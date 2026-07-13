from __future__ import annotations

import io
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

logger = logging.getLogger(__name__)
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
OAUTH_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_DEFAULT_URI = "https://oauth2.googleapis.com/token"


class DriveError(Exception):
    pass


def _token_file_path(account: object | None = None) -> Path:
    account_token_file = getattr(account, "oauth_token_file", None)
    if account_token_file:
        return Path(account_token_file)

    token_file = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE")
    if token_file:
        base_path = Path(token_file)
        if account is not None and getattr(account, "index", 0) > 0:
            return _derive_account_token_file_path(base_path, account.index)
        return base_path

    default_path = Path(__file__).resolve().parent / "instance" / "google_drive_oauth.json"
    if account is not None and getattr(account, "index", 0) > 0:
        return _derive_account_token_file_path(default_path, account.index)
    return default_path


def _account_env_name(name: str, index: int) -> str:
    return name if index == 0 else f"{name}_{index}"


def _dotenv_path() -> Path:
    return Path(__file__).resolve().parent / ".env"


def _write_dotenv_variable(name: str, value: str) -> None:
    dotenv_path = _dotenv_path()
    existing_lines = []
    if dotenv_path.exists():
        existing_lines = dotenv_path.read_text(encoding="utf-8").splitlines()

    normalized_name = f"{name}="
    updated = False
    output_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped.startswith(normalized_name):
            output_lines.append(line)
            continue
        output_lines.append(f"{name}={value}")
        updated = True
    if not updated:
        output_lines.append(f"{name}={value}")

    dotenv_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def _derive_account_token_file_path(path: Path, index: int) -> Path:
    if index == 0:
        return path
    if path.suffix:
        return path.with_name(f"{path.stem}_{index}{path.suffix}")
    return path.with_name(f"{path.name}_{index}")


def _load_refresh_token(account: object | None = None) -> str | None:
    refresh_token = getattr(account, "oauth_refresh_token", None) if account is not None else None
    if refresh_token:
        return refresh_token.strip()

    if account is not None and getattr(account, "index", 0) is not None:
        refresh_token = os.environ.get(_account_env_name("GOOGLE_OAUTH_REFRESH_TOKEN", account.index))
        if refresh_token:
            return refresh_token.strip()

    refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")
    if refresh_token:
        return refresh_token.strip()

    token_path = _token_file_path(account)
    if not token_path.exists():
        return None

    try:
        content = token_path.read_text(encoding="utf-8")
        data = json.loads(content)
        return data.get("refresh_token")
    except Exception as exc:
        logger.exception("Failed to read OAuth refresh token from %s", token_path)
        return None


def save_refresh_token(refresh_token: str, account: object | None = None) -> None:
    token_path = _token_file_path(account)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps({"refresh_token": refresh_token}, indent=2), encoding="utf-8")

    if account is not None and getattr(account, "index", 0) is not None:
        env_key = _account_env_name("GOOGLE_OAUTH_REFRESH_TOKEN", account.index)
    else:
        env_key = "GOOGLE_OAUTH_REFRESH_TOKEN"

    os.environ[env_key] = refresh_token
    try:
        _write_dotenv_variable(env_key, refresh_token)
    except Exception:
        logger.exception("Unable to persist OAuth refresh token to .env file")


def _delete_stored_refresh_token(account: object | None = None) -> None:
    token_path = _token_file_path(account)
    if token_path.exists():
        try:
            token_path.unlink()
            logger.info("Deleted stale Google OAuth refresh token file %s", token_path)
        except Exception:
            logger.exception("Failed to delete stale Google OAuth refresh token file %s", token_path)


def _resolve_service_account_path(service_account_path: str | Path | object | None = None) -> str | Path | None:
    if service_account_path is not None and hasattr(service_account_path, "service_account"):
        service_account_path = getattr(service_account_path, "service_account")
    return service_account_path


def _load_service_account_credentials(service_account_path: str | Path | object | None = None) -> Credentials:
    service_account_path = _resolve_service_account_path(service_account_path)
    if service_account_path is not None:
        service_account_path = Path(service_account_path)
        if service_account_path.exists():
            try:
                return service_account.Credentials.from_service_account_file(
                    str(service_account_path), scopes=DRIVE_SCOPES
                )
            except Exception as exc:
                logger.exception(
                    "Failed to load credentials from service account file %s",
                    service_account_path,
                )
                raise DriveError(
                    "Failed to load Google service account credentials from file."
                ) from exc

    json_value = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if json_value:
        try:
            service_account_info = json.loads(json_value)
            return service_account.Credentials.from_service_account_info(
                service_account_info, scopes=DRIVE_SCOPES
            )
        except Exception as exc:
            logger.exception("Failed to load service account credentials from environment")
            raise DriveError(
                "Invalid GOOGLE_SERVICE_ACCOUNT_JSON value or service account creation failed."
            ) from exc

    raise DriveError(
        "Google service account credentials are not available. Provide a local service account path or GOOGLE_SERVICE_ACCOUNT_JSON."
    )


def _has_service_account_credentials(service_account_path: str | Path | object | None = None) -> bool:
    try:
        _load_service_account_credentials(service_account_path)
        return True
    except DriveError:
        return False


def _load_credentials(service_account_path: str | Path | object | None = None) -> Credentials:
    account = None
    if service_account_path is not None and hasattr(service_account_path, "service_account"):
        account = service_account_path
        service_account_path = getattr(account, "service_account", None)

    client_id = getattr(account, "oauth_client_id", None) if account is not None else None
    client_secret = getattr(account, "oauth_client_secret", None) if account is not None else None
    refresh_token_env = getattr(account, "oauth_refresh_token", None) if account is not None else None
    token_uri = getattr(account, "oauth_token_uri", None) if account is not None else None

    if client_id is None:
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    if client_secret is None:
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if refresh_token_env is None:
        refresh_token_env = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")
    if token_uri is None:
        token_uri = os.environ.get("GOOGLE_OAUTH_TOKEN_URI", OAUTH_TOKEN_DEFAULT_URI)

    refresh_token = _load_refresh_token(account)

    if client_id and client_secret and refresh_token:
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri=token_uri,
            scopes=DRIVE_SCOPES,
        )
        request = Request()
        try:
            if not credentials.valid:
                credentials.refresh(request)
            return credentials
        except RefreshError as exc:
            logger.exception("Google OAuth refresh failed due to invalid grant")
            if not refresh_token_env:
                _delete_stored_refresh_token()
            if _has_service_account_credentials(service_account_path):
                logger.warning(
                    "Falling back to service account credentials because OAuth refresh token is invalid."
                )
                return _load_service_account_credentials(service_account_path)
            raise DriveError(
                "Google OAuth refresh token is invalid or revoked. "
                "Re-authorize via /dashboard/google-oauth/authorize and update your refresh token or token file."
            ) from exc
        except Exception as exc:
            logger.exception("Failed to refresh Google OAuth credentials")
            if _has_service_account_credentials(service_account_path):
                logger.warning(
                    "Falling back to service account credentials because OAuth refresh failed."
                )
                return _load_service_account_credentials(service_account_path)
            raise DriveError(
                f"Unable to obtain Google OAuth credentials: {exc}"
            ) from exc

    if client_id or client_secret or refresh_token_env:
        if _has_service_account_credentials(service_account_path):
            logger.warning(
                "Partial OAuth configuration detected; using service account credentials instead."
            )
            return _load_service_account_credentials(service_account_path)
        raise DriveError(
            "Google OAuth is partially configured. Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REFRESH_TOKEN or complete the authorization flow."
        )

    return _load_service_account_credentials(service_account_path)


def get_oauth_authorization_url(redirect_uri: str, state: str | None = None, account: object | None = None) -> str:
    client_id = getattr(account, "oauth_client_id", None) if account is not None else None
    if not client_id:
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    if not client_id:
        raise DriveError("Google OAuth client ID is not configured.")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(DRIVE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    if state:
        params["state"] = state

    return f"{OAUTH_AUTH_URI}?{urllib.parse.urlencode(params)}"


def exchange_authorization_code(code: str, redirect_uri: str, account: object | None = None) -> dict[str, Any]:
    client_id = getattr(account, "oauth_client_id", None) if account is not None else None
    client_secret = getattr(account, "oauth_client_secret", None) if account is not None else None
    token_uri = getattr(account, "oauth_token_uri", None) if account is not None else None

    if client_id is None:
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    if client_secret is None:
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if token_uri is None:
        token_uri = os.environ.get("GOOGLE_OAUTH_TOKEN_URI", OAUTH_TOKEN_DEFAULT_URI)

    if not client_id or not client_secret:
        raise DriveError("Google OAuth client credentials are not configured.")

    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    request = urllib.request.Request(
        token_uri,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        logger.exception("Google token exchange failed: %s", error_body)
        raise DriveError("Google OAuth token exchange failed.") from exc
    except Exception as exc:
        logger.exception("Google token exchange failed")
        raise DriveError("Google OAuth token exchange failed.") from exc

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise DriveError(
            "Google did not return a refresh token. Authorize again with prompt=consent."
        )

    save_refresh_token(refresh_token, account)
    return token_data


def has_refresh_token(account: object | None = None) -> bool:
    return bool(_load_refresh_token(account))


def _build_service(credentials: Credentials) -> Any:
    try:
        return build("drive", "v3", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        logger.exception("Unable to initialize Google Drive service")
        raise DriveError("Unable to initialize Google Drive service.") from exc


def _get_service(service_account_path: str | Path | None = None) -> Any:
    credentials = _load_credentials(service_account_path)
    return _build_service(credentials)


def upload_file(
    service_account_path: str | Path | None,
    file_path: str | Path,
    mime_type: str,
    folder_id: str,
    name: str,
    make_public: bool = True,
) -> str:
    file_path = Path(file_path)
    if not file_path.exists():
        raise DriveError(f"Upload file does not exist: {file_path}")
    if not folder_id:
        raise DriveError("Google Drive folder ID is required.")

    service = _get_service(service_account_path)
    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
    metadata = {"name": name, "parents": [folder_id]}

    try:
        created = service.files().create(
            body=metadata,
            media_body=media,
            fields="id,webViewLink,webContentLink,thumbnailLink",
        ).execute()
        file_id = created.get("id")
        if not file_id:
            raise DriveError("Google Drive did not return a file ID.")
        if make_public:
            _set_public_permission(service, file_id)
        logger.info(
            "Uploaded file %s to Drive folder %s with id %s",
            name,
            folder_id,
            file_id,
        )
        return file_id
    except HttpError as exc:
        logger.exception("Google Drive upload failed for file %s", name)
        raise DriveError("Google Drive upload failed.") from exc
    except DriveError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during Google Drive upload for file %s", name)
        raise DriveError("Unexpected error during Google Drive upload.") from exc


def upload_poster(service_account_path: str | Path | None, file_path: str | Path, mime_type: str, folder_id: str, name: str) -> str:
    return upload_file(service_account_path, file_path, mime_type, folder_id, name)


def upload_video(service_account_path: str | Path | None, file_path: str | Path, mime_type: str, folder_id: str, name: str) -> str:
    return upload_file(service_account_path, file_path, mime_type, folder_id, name)


def delete_file(service_account_path: str | Path | None, file_id: str) -> bool:
    if not file_id:
        return False
    service = _get_service(service_account_path)
    try:
        service.files().delete(fileId=file_id).execute()
        logger.info("Deleted Google Drive file %s", file_id)
        return True
    except HttpError as exc:
        logger.exception("Google Drive delete failed for file %s", file_id)
        return False
    except Exception:
        logger.exception("Unexpected error deleting Google Drive file %s", file_id)
        return False


def replace_file(
    service_account_path: str | Path | None,
    old_file_id: str | None,
    new_file_path: str | Path,
    mime_type: str,
    folder_id: str,
    name: str,
) -> str:
    new_file_id = upload_file(service_account_path, new_file_path, mime_type, folder_id, name)
    if old_file_id:
        if delete_file(service_account_path, old_file_id):
            logger.info("Replaced Google Drive file %s with new file %s", old_file_id, new_file_id)
        else:
            logger.warning("Failed to delete old Google Drive file %s after replacement.", old_file_id)
    return new_file_id


def get_file_url(file_id: str) -> str:
    if not file_id:
        raise DriveError("File ID is required for download URLs.")
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def download_file(
    service_account_path: str | Path | None,
    file_id: str,
    destination: str | Path,
) -> Path:
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    service = _get_service(service_account_path)
    request = service.files().get_media(fileId=file_id)
    try:
        with destination_path.open("wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return destination_path
    except HttpError as exc:
        logger.exception("Google Drive download failed for file %s", file_id)
        raise DriveError("Google Drive download failed.") from exc
    except Exception as exc:
        logger.exception("Unexpected error during Google Drive download for file %s", file_id)
        raise DriveError("Unexpected error during Google Drive download.") from exc


def download_text(
    service_account_path: str | Path | None,
    file_id: str,
) -> str:
    service = _get_service(service_account_path)
    request = service.files().get_media(fileId=file_id)
    try:
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return file_buffer.getvalue().decode("utf-8")
    except HttpError as exc:
        logger.exception("Google Drive text download failed for file %s", file_id)
        raise DriveError("Google Drive text download failed.") from exc
    except Exception as exc:
        logger.exception("Unexpected error during Google Drive text download for file %s", file_id)
        raise DriveError("Unexpected error during Google Drive text download.") from exc


def upload_text_file(
    service_account_path: str | Path | None,
    content: str,
    folder_id: str,
    name: str,
    mime_type: str = "application/json",
    file_id: str | None = None,
    make_public: bool = False,
) -> str:
    if file_id:
        service = _get_service(service_account_path)
        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype=mime_type, resumable=True)
        try:
            updated = service.files().update(
                fileId=file_id,
                media_body=media,
                fields="id",
            ).execute()
            return updated.get("id") or file_id
        except HttpError as exc:
            logger.exception("Google Drive text file update failed for %s", name)
            raise DriveError("Google Drive text file update failed.") from exc
        except Exception as exc:
            logger.exception("Unexpected error during Google Drive text file update for %s", name)
            raise DriveError("Unexpected error during Google Drive text file update.") from exc

    service = _get_service(service_account_path)
    media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype=mime_type, resumable=True)
    try:
        created = service.files().create(
            body={"name": name, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        file_id = created.get("id")
        if not file_id:
            raise DriveError("Google Drive did not return a file ID.")
        if make_public:
            _set_public_permission(service, file_id)
        return file_id
    except HttpError as exc:
        logger.exception("Google Drive text file upload failed for %s", name)
        raise DriveError("Google Drive text file upload failed.") from exc
    except Exception as exc:
        logger.exception("Unexpected error during Google Drive text file upload for %s", name)
        raise DriveError("Unexpected error during Google Drive text file upload.") from exc


def create_folder(
    service_account_path: str | Path | None,
    name: str,
    parent_id: str | None = None,
) -> str:
    if not name:
        raise DriveError("Folder name is required.")
    service = _get_service(service_account_path)
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    try:
        created = service.files().create(body=metadata, fields="id").execute()
        folder_id = created.get("id")
        if not folder_id:
            raise DriveError("Google Drive did not return a folder ID.")
        logger.info("Created Google Drive folder %s under parent %s", name, parent_id)
        return folder_id
    except HttpError as exc:
        logger.exception("Google Drive folder creation failed for %s", name)
        raise DriveError("Google Drive folder creation failed.") from exc
    except Exception as exc:
        logger.exception("Unexpected error creating Google Drive folder %s", name)
        raise DriveError("Unexpected error during Google Drive folder creation.") from exc


def list_files(
    service_account_path: str | Path | None,
    q: str,
    fields: str = "files(id,name,mimeType,createdTime,size)",
    page_size: int = 100,
) -> list[dict[str, Any]]:
    service = _get_service(service_account_path)
    try:
        response = service.files().list(q=q, fields=fields, pageSize=page_size).execute()
        return response.get("files", []) or []
    except HttpError as exc:
        logger.exception("Failed to list Google Drive files using query %s", q)
        raise DriveError("Google Drive file listing failed.") from exc
    except Exception as exc:
        logger.exception("Unexpected error listing Google Drive files %s", q)
        raise DriveError("Unexpected error during Google Drive file listing.") from exc


def get_file_image_url(file_id: str) -> str:
    if not file_id:
        raise DriveError("File ID is required for image URLs.")
    return f"https://lh3.googleusercontent.com/d/{file_id}"


def build_google_drive_image_url(file_id: str) -> str:
    return get_file_image_url(file_id)


def ensure_public_permission(service_account_path: str | Path | None, file_id: str) -> None:
    if not file_id:
        raise DriveError("File ID is required to ensure Drive permissions.")
    service = _get_service(service_account_path)
    _set_public_permission(service, file_id)


def get_file_view_url(file_id: str) -> str:
    if not file_id:
        raise DriveError("File ID is required for view URLs.")
    return f"https://drive.google.com/uc?export=view&id={file_id}"


def _escape_drive_query_value(value: str) -> str:
    return value.replace("'", "\\'")


def search_file_id_by_name(
    service_account_path: str | Path | None,
    name: str,
    *,
    folder_id: str | None = None,
    mime_type_prefix: str | None = None,
    size: int | None = None,
) -> str | None:
    if not name:
        return None

    service = _get_service(service_account_path)
    query_parts = [f"name = '{_escape_drive_query_value(Path(name).name)}'", "trashed = false"]
    if folder_id:
        query_parts.append(f"'{_escape_drive_query_value(folder_id)}' in parents")
    if mime_type_prefix:
        query_parts.append(f"mimeType contains '{_escape_drive_query_value(mime_type_prefix)}'")

    query = " and ".join(query_parts)
    try:
        response = (
            service.files()
            .list(
                q=query,
                fields="files(id,name,size,createdTime)",
                orderBy="createdTime desc",
                pageSize=10,
            )
            .execute()
        )
        candidates = response.get("files", []) or []
        if not candidates:
            return None

        if size is not None:
            for candidate in candidates:
                candidate_size = candidate.get("size")
                try:
                    if candidate_size is not None and int(candidate_size) == size:
                        return candidate.get("id")
                except (TypeError, ValueError):
                    continue

        return candidates[0].get("id")
    except HttpError:
        logger.exception("Failed to search Google Drive for file %s", name)
        return None
    except Exception:
        logger.exception("Unexpected error searching Google Drive for file %s", name)
        return None


def get_file_metadata(service_account_path: str | Path | None, file_id: str) -> dict[str, Any] | None:
    if not file_id:
        return None
    service = _get_service(service_account_path)
    try:
        return service.files().get(fileId=file_id, fields="id,name,mimeType,size,createdTime,modifiedTime").execute()
    except HttpError as exc:
        logger.exception("Failed to retrieve metadata for Google Drive file %s", file_id)
        return None
    except Exception:
        logger.exception("Unexpected error retrieving metadata for Google Drive file %s", file_id)
        return None


def exists(service_account_path: str | Path | None, file_id: str) -> bool:
    return get_file_metadata(service_account_path, file_id) is not None


def get_file_id(value: str | None) -> str | None:
    if not value:
        return None
    value = urllib.parse.unquote(value.strip())
    if value.startswith("http://") or value.startswith("https://"):
        for pattern in [
            r"/file/d/([A-Za-z0-9_.-]{20,})",
            r"/d/([A-Za-z0-9_.-]{20,})",
            r"[?&]id=([A-Za-z0-9_.-]{20,})",
        ]:
            match = re.search(pattern, value)
            if match:
                return match.group(1)
        return None
    return value


def is_drive_file_id(value: str | None) -> bool:
    file_id = get_file_id(value)
    if not file_id:
        return False
    if "/" in file_id:
        return False
    if len(file_id) < 20:
        return False
    # Google Drive file IDs are URL-safe base64-ish strings and may include dashes, underscores, and dots.
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+", file_id))


def _set_public_permission(service: Any, file_id: str) -> None:
    try:
        existing_permissions = (
            service.permissions()
            .list(fileId=file_id, fields="permissions(id,type,role)")
            .execute()
            .get("permissions", [])
        )
        for permission in existing_permissions:
            if permission.get("type") == "anyone" and permission.get("role") == "reader":
                logger.debug("Google Drive file %s already has public read permission", file_id)
                return

        body = {"type": "anyone", "role": "reader"}
        service.permissions().create(fileId=file_id, body=body).execute()
    except HttpError as exc:
        logger.exception("Failed to set public permission for Google Drive file %s", file_id)
        raise DriveError("Could not make Google Drive file publicly accessible.") from exc
    except Exception as exc:
        logger.exception("Unexpected error setting Google Drive permissions for %s", file_id)
        raise DriveError("Could not make Google Drive file publicly accessible.") from exc
