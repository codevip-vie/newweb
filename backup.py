from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import google_drive
from storage import storage_manager

BACKUP_INTERVAL_SECONDS = 600
MAX_BACKUPS = 5
SCHEMA_VERSION = 1
APPLICATION_VERSION = "1.0.0"
REQUIRED_TABLES = {"users", "movies", "posters", "founders"}
SYSTEM_FOLDER_NAMES = {
    "database": "database",
    "metadata": "metadata",
    "logs": "logs",
    "version": "version",
}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _atomic_write_json(path: Path, data: Any) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    text = json.dumps(data, indent=2)
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    temp_path.replace(path)


class BackupManager:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.root_dir = Path(__file__).resolve().parent
        self.metadata_dir = self.root_dir / "metadata"
        self.version_dir = self.root_dir / "version"
        self.logs_dir = self.root_dir / "logs"
        self.state_path = self.metadata_dir / "database_state.json"
        self.folders_cache_path = self.metadata_dir / "folders.json"
        self.latest_path = self.metadata_dir / "latest.json"
        self.log_path = self.logs_dir / "backup.log"
        self.database_path = Path(app.config["DATABASE_PATH"])
        self.instance_dir = Path(app.config["INSTANCE_DIR"])
        self.backup_temp_dir = self.instance_dir / "backup_tmp"
        self.account0 = storage_manager.get_account(0)
        self.system_folder_id = (
            app.config.get("GOOGLE_DRIVE_SYSTEM_FOLDER_ID")
            or getattr(self.account0, "system_folder_id", None)
        )

        self._operation_lock = threading.RLock()
        self.state = "IDLE"
        self.dirty = False
        self.generation = 0
        self.database_uuid = ""
        self.device_id = ""
        self.environment_type = self._detect_environment_type()
        self.generation_updated_at = _utc_iso()
        self.last_backup_status = "unknown"
        self.last_backup_time: str | None = None
        self.last_backup_message = "Backup has not run yet."
        self.last_restore_status = "unknown"
        self.last_restore_time: str | None = None
        self.last_restore_message = "Restore has not run yet."
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        _ensure_directory(self.metadata_dir)
        _ensure_directory(self.version_dir)
        _ensure_directory(self.logs_dir)
        _ensure_directory(self.backup_temp_dir)
        self._initialize_version_file()
        self._load_or_initialize_state()

    def setup(self) -> None:
        with self._operation_lock:
            self._log("Backup manager initialized.")
            self.perform_startup_restore()
            self.start_backup_thread()

    def _detect_environment_type(self) -> str:
        railway_env = os.environ.get("RAILWAY_ENVIRONMENT")
        if railway_env:
            return "railway-production" if railway_env.lower() == "production" else "railway-staging"
        if os.environ.get("RAILWAY_STATIC_URL"):
            return "railway-production"
        if os.environ.get("FLASK_ENV"):
            return f"flask-{os.environ.get('FLASK_ENV').lower()}"
        return "local-development"

    def _initialize_version_file(self) -> None:
        schema_file = self.version_dir / "schema.json"
        if not schema_file.exists():
            _atomic_write_json(
                schema_file,
                {
                    "database": "sqlite",
                    "schema_version": SCHEMA_VERSION,
                    "application": APPLICATION_VERSION,
                },
            )

    def _load_or_initialize_state(self) -> None:
        state = self._read_state_file() or {}
        if not state.get("database_uuid"):
            state["database_uuid"] = uuid.uuid4().hex
        if not state.get("device_id"):
            state["device_id"] = uuid.uuid4().hex
        state["environment_type"] = self.environment_type
        state["generation"] = int(state.get("generation", 0))
        state["generation_updated_at"] = state.get("generation_updated_at") or _utc_iso()
        self.database_uuid = state["database_uuid"]
        self.device_id = state["device_id"]
        self.environment_type = state["environment_type"]
        self.generation = state["generation"]
        self.generation_updated_at = state["generation_updated_at"]
        self._write_state_file(state)

    def _read_state_file(self) -> dict[str, Any] | None:
        try:
            if self.state_path.exists():
                return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return None

    def _write_state_file(self, state: dict[str, Any]) -> None:
        _atomic_write_json(self.state_path, state)

    def start_backup_thread(self) -> None:
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        self._worker_thread = threading.Thread(target=self._backup_worker, daemon=True)
        self._worker_thread.start()

    def _backup_worker(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(BACKUP_INTERVAL_SECONDS)
            try:
                self.create_backup_if_dirty()
            except Exception as exc:
                self._log(f"Backup worker error: {exc}")

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=1)

    def _begin_operation(self, operation: str) -> bool:
        if self.state != "IDLE":
            self._log(f"Operation {operation} blocked because state is {self.state}.")
            return False
        self.state = operation
        return True

    def _end_operation(self) -> None:
        self.state = "IDLE"

    def _set_status(self, kind: str, status: str, message: str) -> None:
        if kind == "backup":
            self.last_backup_status = status
            self.last_backup_time = _utc_iso()
            self.last_backup_message = message
        elif kind == "restore":
            self.last_restore_status = status
            self.last_restore_time = _utc_iso()
            self.last_restore_message = message

    def _log(self, message: str, *args: object) -> None:
        if args:
            try:
                message = message % args
            except Exception:
                message = f"{message} {args}"
        timestamp = _utc_iso()
        log_line = f"[{timestamp}] {message}\n"
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.open("a", encoding="utf-8").write(log_line)
        except Exception:
            pass
        try:
            if hasattr(self.app, "logger"):
                self.app.logger.info(message)
        except Exception:
            pass

    def _has_system_folder(self) -> bool:
        return bool(self.system_folder_id)

    def _load_folder_cache(self) -> dict[str, str] | None:
        try:
            if self.folders_cache_path.exists():
                data = json.loads(self.folders_cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("system_folder_id") == self.system_folder_id:
                    return data
        except Exception:
            pass
        return None

    def _save_folder_cache(self, ids: dict[str, str]) -> None:
        ids["last_updated"] = _utc_iso()
        _atomic_write_json(self.folders_cache_path, ids)

    def _ensure_system_folders(self) -> dict[str, str]:
        ids = self._load_folder_cache()
        if ids is None or ids.get("system_folder_id") != self.system_folder_id:
            ids = {"system_folder_id": self.system_folder_id}
        ids = self._ensure_folder_ids(ids)
        self._save_folder_cache(ids)
        return ids

    def _verify_folder_exists(self, folder_id: str, label: str) -> bool:
        try:
            if not folder_id:
                return False
            return google_drive.exists(self.account0, folder_id)
        except Exception:
            return False

    def _ensure_folder_ids(self, ids: dict[str, str]) -> dict[str, str]:
        root_id = ids["system_folder_id"]
        if not root_id or not self._verify_folder_exists(root_id, "system"):
            raise RuntimeError(
                "Configured Google Drive system folder ID does not exist or is inaccessible."
            )
        for name in SYSTEM_FOLDER_NAMES.values():
            folder_id = ids.get(f"{name}_folder_id")
            if not folder_id or not self._verify_folder_exists(folder_id, name):
                folder_id = self._find_or_create_folder(name, root_id)
            ids[f"{name}_folder_id"] = folder_id
        return ids

    def _find_or_create_folder(self, folder_name: str, parent_id: str) -> str:
        existing_id = google_drive.search_file_id_by_name(
            self.account0,
            folder_name,
            folder_id=parent_id,
            mime_type_prefix="application/vnd.google-apps.folder",
        )
        if existing_id:
            return existing_id
        return google_drive.create_folder(self.account0, folder_name, parent_id)

    def perform_startup_restore(self) -> bool:
        if not self._has_system_folder():
            self._set_status("restore", "skipped", "Restore skipped: system folder ID is not configured.")
            self._log("Restore skipped: system folder ID is not configured.")
            return False

        with self._operation_lock:
            if not self._begin_operation("RESTORING"):
                return False
            try:
                self._log("Restore started.")
                ids = self._ensure_system_folders()
                latest_metadata = self._load_remote_latest(ids["metadata_folder_id"])
                if latest_metadata is None:
                    self._log("latest.json unavailable; attempting metadata recovery from backup files.")
                    latest_metadata = self._recover_latest_metadata(ids["database_folder_id"])
                if latest_metadata is None:
                    self._set_status("restore", "skipped", "No recoverable backup metadata was found.")
                    self._log("Restore skipped: no recoverable latest metadata.")
                    return False

                local_db_valid = self.database_path.exists() and self._validate_sqlite(self.database_path, require_tables=True)
                local_generation = self.generation
                local_sqlite_metadata = None
                if local_db_valid:
                    local_sqlite_metadata = self._read_sqlite_metadata(self.database_path)
                    if local_sqlite_metadata is not None:
                        try:
                            local_generation = int(local_sqlite_metadata.get("generation", local_generation))
                        except (TypeError, ValueError):
                            pass
                        if local_generation != self.generation:
                            self.generation = local_generation

                cloud_generation = None
                try:
                    cloud_generation = int(latest_metadata.get("database_generation", 0))
                except (TypeError, ValueError):
                    cloud_generation = None

                self._log(
                    "Restore metadata: cloud_generation=%s, cloud_db_uuid=%s, local_exists=%s, local_valid=%s, local_generation=%s, state_generation=%s",
                    cloud_generation,
                    latest_metadata.get("database_uuid"),
                    self.database_path.exists(),
                    local_db_valid,
                    local_generation,
                    self.generation,
                )

                if cloud_generation is None:
                    self._set_status("restore", "skipped", "Cloud backup generation unknown; restore skipped.")
                    self._log("Restore skipped: cloud backup generation unknown.")
                    return False

                if local_db_valid and local_generation >= cloud_generation:
                    self._set_status("restore", "skipped", "Database already exists and is valid; restore is not required.")
                    self._log(
                        "Restore skipped: local database is valid and up to date (local=%s, cloud=%s).",
                        local_generation,
                        cloud_generation,
                    )
                    return False

                if local_db_valid:
                    self._log(
                        "Local database is valid but out of date (local=%s, cloud=%s); restoring latest cloud backup.",
                        local_generation,
                        cloud_generation,
                    )
                elif self.database_path.exists():
                    self._log("Existing database is invalid or incomplete; attempting restore from latest cloud backup.")
                else:
                    self._log("No local database found; restoring latest cloud backup.")

                try:
                    self._restore_backup(latest_metadata, ids)
                except RuntimeError as exc:
                    self._log("Restore failed using latest metadata: %s", exc)
                    if "Downloaded backup file is not a valid SQLite database." in str(exc) or "SHA256 mismatch" in str(exc):
                        self._log("Attempting recovery from other backup files because latest cloud backup appears invalid.")
                        recovered_metadata = self._recover_latest_metadata(ids["database_folder_id"])
                        if recovered_metadata is not None:
                            self._log(
                                "Found recoverable backup file %s from Drive.",
                                recovered_metadata.get("backup_filename"),
                            )
                            self._restore_backup(recovered_metadata, ids)
                        else:
                            raise
                    else:
                        raise

                self._set_status("restore", "success", "Restore completed from the latest backup.")
                self._log("Restore completed.")
                return True
            except Exception as exc:
                self._set_status("restore", "fail", f"Restore failed: {exc}")
                self._log(f"Restore failed: {exc}")
                return False
            finally:
                self._end_operation()

    def _recover_latest_metadata(self, database_folder_id: str) -> dict[str, Any] | None:
        query = f"'{database_folder_id}' in parents and trashed = false"
        files = google_drive.list_files(self.account0, query, fields="files(id,name,size)")
        candidates: list[dict[str, Any]] = []
        for file in files:
            parsed = self._parse_backup_filename(file.get("name", ""))
            if parsed is None:
                continue
            parsed["id"] = file.get("id")
            parsed["size"] = int(file.get("size", 0)) if file.get("size") is not None else 0
            candidates.append(parsed)
        if not candidates:
            return None
        candidates.sort(key=lambda entry: (entry.get("generation", 0), entry.get("backup_created_at", "")), reverse=True)
        for candidate in candidates:
            temp_path = self.backup_temp_dir / f"recover_{candidate['backup_name']}"
            try:
                _ensure_directory(temp_path.parent)
                google_drive.download_file(self.account0, candidate["id"], temp_path)
                sql_metadata = self._read_sqlite_metadata(temp_path)
                if sql_metadata and int(sql_metadata.get("generation", 0)) == int(candidate["generation"]):
                    recovered = {
                        "backup_file_id": candidate["id"],
                        "backup_filename": candidate["backup_name"],
                        "database_generation": int(sql_metadata.get("generation", 0)),
                        "database_uuid": sql_metadata.get("database_uuid", self.database_uuid),
                        "sha256": self._hash_file(temp_path) or "",
                        "schema_version": sql_metadata.get("schema_version", SCHEMA_VERSION),
                        "application_version": sql_metadata.get("application_version", APPLICATION_VERSION),
                        "backup_created_at": sql_metadata.get("backup_created_at", candidate.get("backup_created_at", _utc_iso())),
                        "device_id": self.device_id,
                        "environment_type": self.environment_type,
                        "database_size": temp_path.stat().st_size,
                    }
                    self._log(f"Recovered latest metadata from backup file {candidate['backup_name']}")
                    return recovered
            except Exception:
                pass
            finally:
                temp_path.unlink(missing_ok=True)
        return None

    def _load_remote_latest(self, metadata_folder_id: str) -> dict[str, Any] | None:
        latest_id = self._find_metadata_file_id("latest.json", metadata_folder_id)
        if not latest_id:
            return None
        try:
            text = google_drive.download_text(self.account0, latest_id)
            latest = json.loads(text)
            if isinstance(latest, dict):
                return latest
        except Exception:
            pass
        return None

    def _find_metadata_file_id(self, name: str, folder_id: str) -> str | None:
        return google_drive.search_file_id_by_name(
            self.account0,
            name,
            folder_id=folder_id,
            mime_type_prefix="application/json",
        )

    def _restore_backup(self, latest_metadata: dict[str, Any], ids: dict[str, str]) -> None:
        database_folder_id = ids["database_folder_id"]
        metadata_folder_id = ids["metadata_folder_id"]
        file_id = latest_metadata.get("backup_file_id")
        if not file_id:
            raise RuntimeError("Restore metadata does not include a backup file ID.")
        temp_restore_path = self.backup_temp_dir / f"restore_{latest_metadata.get('backup_filename', _utc_timestamp())}.sqlite3"
        _ensure_directory(temp_restore_path.parent)
        google_drive.download_file(self.account0, file_id, temp_restore_path)
        if latest_metadata.get("sha256"):
            actual_sha256 = self._hash_file(temp_restore_path)
            if actual_sha256 != latest_metadata.get("sha256"):
                temp_restore_path.unlink(missing_ok=True)
                raise RuntimeError("Downloaded backup file SHA256 mismatch.")
        if not self._validate_sqlite(temp_restore_path, require_tables=True):
            temp_restore_path.unlink(missing_ok=True)
            raise RuntimeError("Downloaded backup file is not a valid SQLite database.")

        self._validate_restore_metadata(latest_metadata)
        actual_db_path = self.database_path
        backup_old = actual_db_path.with_name(f"{actual_db_path.name}.old")
        if actual_db_path.exists():
            actual_db_path.replace(backup_old)
        _ensure_directory(actual_db_path.parent)
        temp_restore_path.replace(actual_db_path)
        if backup_old.exists():
            backup_old.unlink(missing_ok=True)
        self._apply_restored_state(latest_metadata)


    def _validate_restore_metadata(self, metadata: dict[str, Any]) -> None:
        if metadata.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError("Backup schema version does not match application schema.")

        if self.database_path.exists() and self._validate_sqlite(self.database_path, require_tables=True):
            local_metadata = self._read_sqlite_metadata(self.database_path)
            if local_metadata is not None:
                local_uuid = local_metadata.get("database_uuid")
                if local_uuid and metadata.get("database_uuid") and local_uuid != metadata.get("database_uuid"):
                    raise RuntimeError("Backup database UUID does not match the current local database UUID.")

    def _create_sqlite_backup(self, source: Path, destination: Path) -> None:
        if destination.exists():
            destination.unlink(missing_ok=True)
        _ensure_directory(destination.parent)
        source_conn = sqlite3.connect(source)
        try:
            dest_conn = sqlite3.connect(destination)
            try:
                source_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        finally:
            source_conn.close()

    def _apply_restored_state(self, metadata: dict[str, Any]) -> None:
        state = {
            "database_uuid": metadata.get("database_uuid", self.database_uuid),
            "generation": int(metadata.get("database_generation", 0)),
            "generation_updated_at": metadata.get("backup_created_at", _utc_iso()),
            "device_id": metadata.get("device_id", self.device_id),
            "environment_type": metadata.get("environment_type", self.environment_type),
        }
        self.database_uuid = state["database_uuid"]
        self.generation = state["generation"]
        self.generation_updated_at = state["generation_updated_at"]
        self.device_id = state["device_id"]
        self.environment_type = state["environment_type"]
        self._write_state_file(state)

    def _validate_sqlite(self, database_path: Path, require_tables: bool = False) -> bool:
        try:
            if not database_path.exists() or database_path.stat().st_size == 0:
                self._log("SQLite validation failed: file missing or empty: %s", database_path)
                return False
            conn = sqlite3.connect(database_path)
            cursor = conn.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
            if result is None or result[0] != "ok":
                self._log(
                    "SQLite validation failed: integrity_check returned %s for %s",
                    result,
                    database_path,
                )
                conn.close()
                return False
            if require_tables:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                conn.close()
                missing = REQUIRED_TABLES - tables
                if missing:
                    self._log(
                        "SQLite validation failed: missing required tables %s in %s",
                        missing,
                        database_path,
                    )
                    return False
                return True
            conn.close()
            return True
        except Exception as exc:
            self._log("SQLite validation error for %s: %s", database_path, exc)
            return False

    def mark_dirty(self) -> None:
        with self._operation_lock:
            self.dirty = True
            self._increment_generation()
            self._write_state_file(
                {
                    "database_uuid": self.database_uuid,
                    "device_id": self.device_id,
                    "environment_type": self.environment_type,
                    "generation": self.generation,
                    "generation_updated_at": self.generation_updated_at,
                }
            )

    def _increment_generation(self) -> None:
        self.generation += 1
        self.generation_updated_at = _utc_iso()

    def create_backup_now(self) -> bool:
        return self._perform_backup(force=True)

    def create_backup_if_dirty(self) -> bool:
        if not self.dirty:
            return False
        return self._perform_backup(force=False)

    def _perform_backup(self, force: bool = False) -> bool:
        with self._operation_lock:
            if self.state != "IDLE":
                self._log("Backup skipped because another backup or restore is running.")
                return False
            if not self._has_system_folder():
                self._set_status("backup", "skipped", "Backup skipped: system folder ID is not configured.")
                self._log("Backup skipped: system folder ID is not configured.")
                return False
            if not self.database_path.exists():
                self._set_status("backup", "skipped", "Backup skipped: database file does not exist.")
                self._log("Backup skipped: database file does not exist.")
                return False
            if not force and not self.dirty:
                return False
            if not self._begin_operation("RUNNING"):
                return False
            temp_backup_path = None
            try:
                ids = self._ensure_system_folders()
                database_folder_id = ids["database_folder_id"]
                metadata_folder_id = ids["metadata_folder_id"]
                if not self._validate_sqlite(self.database_path, require_tables=True):
                    raise RuntimeError("Local database validation failed before backup.")
                cloud_generation = self._get_cloud_generation(metadata_folder_id)
                if cloud_generation is not None and self.generation < cloud_generation:
                    self._set_status(
                        "backup",
                        "skipped",
                        "Backup cancelled because a newer cloud backup exists.",
                    )
                    self._log("Backup cancelled because a newer cloud backup exists.")
                    return False
                backup_name = f"movie_manager_{self.generation}_{_utc_timestamp()}.sqlite3"
                temp_backup_path = self.backup_temp_dir / backup_name
                _ensure_directory(temp_backup_path.parent)
                self._create_sqlite_backup(self.database_path, temp_backup_path)
                backup_created_at = _utc_iso()
                sqlite_metadata = {
                    "database_uuid": self.database_uuid,
                    "generation": self.generation,
                    "schema_version": SCHEMA_VERSION,
                    "application_version": APPLICATION_VERSION,
                    "backup_created_at": backup_created_at,
                }
                self._write_sqlite_metadata(temp_backup_path, sqlite_metadata)
                sha256 = self._hash_file(temp_backup_path)
                if sha256 is None:
                    raise RuntimeError("Unable to compute backup hash.")
                file_id = google_drive.upload_file(
                    self.account0,
                    temp_backup_path,
                    "application/x-sqlite3",
                    database_folder_id,
                    backup_name,
                    make_public=False,
                )
                if not file_id:
                    raise RuntimeError("Google Drive did not return a file ID for the backup.")
                metadata = google_drive.get_file_metadata(self.account0, file_id)
                if metadata is None or int(metadata.get("size", 0)) <= 0:
                    raise RuntimeError("Uploaded backup file is empty or missing.")
                latest_data = self._build_latest_metadata(
                    backup_name,
                    file_id,
                    sha256,
                    temp_backup_path.stat().st_size,
                )
                self._update_latest_metadata(latest_data, metadata_folder_id)
                self._prune_old_backups(database_folder_id)
                message = f"Backup finished: {backup_name} uploaded successfully."
                self._set_status("backup", "success", message)
                self._log(
                    f"Backup finished: generation={self.generation} sha256={sha256} size={temp_backup_path.stat().st_size}"
                )
                self.dirty = False
                return True
            except Exception as exc:
                self._set_status("backup", "fail", f"Backup failed: {exc}")
                self._log(f"Backup failed: {exc}")
                return False
            finally:
                if temp_backup_path is not None and temp_backup_path.exists():
                    try:
                        temp_backup_path.unlink()
                    except Exception:
                        pass
                self._end_operation()

    def _get_cloud_generation(self, metadata_folder_id: str) -> int | None:
        latest_metadata = self._load_remote_latest(metadata_folder_id)
        if latest_metadata is not None:
            try:
                return int(latest_metadata.get("database_generation", 0))
            except (TypeError, ValueError):
                return None
        return None

    def _hash_file(self, path: Path) -> str | None:
        try:
            sha = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8192), b""):
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception:
            return None

    def _build_latest_metadata(
        self,
        backup_name: str,
        file_id: str,
        sha256: str,
        database_size: int,
    ) -> dict[str, Any]:
        return {
            "database_uuid": self.database_uuid,
            "database_generation": self.generation,
            "backup_file_id": file_id,
            "backup_filename": backup_name,
            "sha256": sha256,
            "schema_version": SCHEMA_VERSION,
            "application_version": APPLICATION_VERSION,
            "backup_created_at": _utc_iso(),
            "device_id": self.device_id,
            "environment_type": self.environment_type,
            "database_size": database_size,
        }

    def _write_sqlite_metadata(self, database_path: Path, metadata: dict[str, Any]) -> None:
        try:
            connection = sqlite3.connect(database_path)
            cursor = connection.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS backup_metadata (metadata_key TEXT PRIMARY KEY, metadata_value TEXT)"
            )
            for key, value in metadata.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO backup_metadata (metadata_key, metadata_value) VALUES (?, ?)",
                    (key, str(value) if value is not None else ""),
                )
            connection.commit()
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def _read_sqlite_metadata(self, database_path: Path) -> dict[str, Any] | None:
        try:
            connection = sqlite3.connect(database_path)
            cursor = connection.cursor()
            cursor.execute("SELECT metadata_key, metadata_value FROM backup_metadata")
            rows = cursor.fetchall()
            connection.close()
            if not rows:
                return None
            return {key: value for key, value in rows}
        except Exception:
            return None

    def _update_latest_metadata(self, latest_data: dict[str, Any], metadata_folder_id: str) -> None:
        local_latest = None
        try:
            if self.latest_path.exists():
                local_latest = self.latest_path.read_text(encoding="utf-8")
            _atomic_write_json(self.latest_path, latest_data)
            self._write_remote_latest(latest_data, metadata_folder_id)
        except Exception:
            if local_latest is not None:
                self.latest_path.write_text(local_latest, encoding="utf-8")
            raise

    def _write_remote_latest(self, latest_data: dict[str, Any], metadata_folder_id: str) -> None:
        latest_id = self._find_metadata_file_id("latest.json", metadata_folder_id)
        old_latest = None
        try:
            if latest_id:
                old_latest = google_drive.download_text(self.account0, latest_id)
        except Exception:
            old_latest = None

        try:
            latest_id = google_drive.upload_text_file(
                self.account0,
                json.dumps(latest_data, indent=2),
                metadata_folder_id,
                "latest.json",
                mime_type="application/json",
                file_id=latest_id,
                make_public=False,
            )
        except Exception:
            if old_latest is not None and latest_id is not None:
                try:
                    google_drive.upload_text_file(
                        self.account0,
                        old_latest,
                        metadata_folder_id,
                        "latest.json",
                        mime_type="application/json",
                        file_id=latest_id,
                        make_public=False,
                    )
                except Exception:
                    pass
            raise

    def _load_remote_latest(self, metadata_folder_id: str) -> dict[str, Any] | None:
        latest_id = self._find_metadata_file_id("latest.json", metadata_folder_id)
        if not latest_id:
            return None
        try:
            text = google_drive.download_text(self.account0, latest_id)
            latest = json.loads(text)
            if isinstance(latest, dict):
                return latest
        except Exception:
            pass
        return None

    def _prune_old_backups(self, database_folder_id: str) -> set[str]:
        query = f"'{database_folder_id}' in parents and trashed = false"
        files = google_drive.list_files(self.account0, query, fields="files(id,name,size)")
        backup_files: list[dict[str, Any]] = []
        for file in files:
            name = file.get("name", "")
            if not name.endswith(".sqlite3"):
                continue
            parsed = self._parse_backup_filename(name)
            if parsed is None:
                continue
            parsed["id"] = file.get("id")
            parsed["name"] = name
            parsed["size"] = int(file.get("size", 0)) if file.get("size") is not None else 0
            backup_files.append(parsed)
        if len(backup_files) <= MAX_BACKUPS:
            return {entry["name"] for entry in backup_files if entry.get("name")}
        backup_files.sort(key=lambda entry: (entry.get("generation", 0), entry.get("backup_created_at", "")))
        to_delete = backup_files[: len(backup_files) - MAX_BACKUPS]
        for file_info in to_delete:
            if file_info.get("id"):
                google_drive.delete_file(self.account0, file_info["id"])
            self._log(f"Backup deleted: {file_info.get('name')}")
        remaining_files = backup_files[len(to_delete) :]
        return {entry["name"] for entry in remaining_files if entry.get("name")}

    def _parse_backup_filename(self, name: str) -> dict[str, Any] | None:
        prefix = "movie_manager_"
        suffix = ".sqlite3"
        if not name.startswith(prefix) or not name.endswith(suffix):
            return None
        payload = name[len(prefix) : -len(suffix)]
        parts = payload.split("_", 1)
        if len(parts) != 2:
            return {"backup_name": name, "generation": 0, "backup_created_at": ""}
        generation_part, backup_created_at = parts
        try:
            generation = int(generation_part)
        except ValueError:
            return {"backup_name": name, "generation": 0, "backup_created_at": ""}
        return {"backup_name": name, "generation": generation, "backup_created_at": backup_created_at}

