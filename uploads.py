from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg"}
ALLOWED_IMAGE_EXTENSIONS_ALL = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
ALLOWED_IMAGE_MIMES_ALL = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
}
ALLOWED_VIDEO_EXTENSIONS = {"mp4"}
ALLOWED_VIDEO_MIMES = {"video/mp4"}
ALLOWED_FILE_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "bmp",
    "pdf",
    "txt",
    "json",
    "csv",
    "zip",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
}
ALLOWED_FILE_MIMES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "application/pdf",
    "text/plain",
    "application/json",
    "text/csv",
    "application/zip",
    "application/x-zip-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class UploadError(ValueError):
    pass


@dataclass(frozen=True)
class SavedUpload:
    filename: str
    original_name: str
    size: int
    mime_type: str


@dataclass(frozen=True)
class StagedUpload:
    temp_path: Path
    original_name: str
    size: int
    mime_type: str


def ensure_upload_dirs(config: dict[str, object]) -> None:
    temp_dir = _path_value(config.get("UPLOAD_TMP_DIR"), config["INSTANCE_DIR"] / "uploads" / ".tmp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_temp_dir(temp_dir)

    avatar_dir = _path_value(config.get("AVATAR_UPLOAD_DIR"), config["UPLOAD_ROOT"] / "avatars")
    avatar_dir.mkdir(parents=True, exist_ok=True)

    chat_dir = _path_value(config.get("CHAT_UPLOAD_DIR"), config["UPLOAD_ROOT"] / "chat_attachments")
    chat_dir.mkdir(parents=True, exist_ok=True)


def stage_upload(
    storage: FileStorage | None,
    *,
    allowed_extensions: set[str],
    allowed_mimes: set[str],
    max_bytes: int,
    label: str,
    temp_dir: str | Path | None = None,
) -> StagedUpload:
    if storage is None or not storage.filename:
        raise UploadError(f"{label} is required.")

    original_name = secure_filename(storage.filename)
    if not original_name:
        raise UploadError(f"{label} filename is invalid.")

    extension = _extension(original_name)
    if extension not in allowed_extensions:
        raise UploadError(
            f"{label} must use one of these extensions: {', '.join(sorted(allowed_extensions))}."
        )

    client_mime = (storage.mimetype or "").lower()
    if client_mime not in allowed_mimes:
        raise UploadError(f"{label} MIME type is not allowed.")

    temp_directory = Path(temp_dir) if temp_dir else Path(tempfile.gettempdir())
    temp_directory.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None

    try:
        storage.stream.seek(0)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="upload-",
            suffix=".part",
            dir=str(temp_directory),
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

        storage.save(str(temp_path))
        size = temp_path.stat().st_size
        if size == 0:
            raise UploadError(f"{label} cannot be empty.")
        if size > max_bytes:
            raise UploadError(f"{label} exceeds the allowed size.")

        detected_mime = sniff_mime(temp_path)
        if detected_mime not in allowed_mimes:
            raise UploadError(f"{label} content does not match the allowed MIME types.")

        return StagedUpload(
            temp_path=temp_path,
            original_name=original_name,
            size=size,
            mime_type=detected_mime,
        )
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def save_upload(
    storage: FileStorage | None,
    destination: str | Path,
    *,
    allowed_extensions: set[str],
    allowed_mimes: set[str],
    max_bytes: int,
    label: str,
    temp_dir: str | Path | None = None,
) -> SavedUpload:
    if storage is None or not storage.filename:
        raise UploadError(f"{label} is required.")

    original_name = secure_filename(storage.filename)
    if not original_name:
        raise UploadError(f"{label} filename is invalid.")

    extension = _extension(original_name)
    if extension not in allowed_extensions:
        raise UploadError(
            f"{label} must use one of these extensions: {', '.join(sorted(allowed_extensions))}."
        )

    client_mime = (storage.mimetype or "").lower()
    if client_mime not in allowed_mimes:
        raise UploadError(f"{label} MIME type is not allowed.")

    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)

    temp_directory = Path(temp_dir) if temp_dir else destination_path.parent / ".tmp"
    temp_directory.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    final_name = f"{uuid4().hex}.{extension}"
    final_path = destination_path / final_name

    try:
        storage.stream.seek(0)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="upload-",
            suffix=".part",
            dir=str(temp_directory),
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

        storage.save(str(temp_path))
        size = temp_path.stat().st_size
        if size == 0:
            raise UploadError(f"{label} cannot be empty.")
        if size > max_bytes:
            raise UploadError(f"{label} exceeds the allowed size.")

        detected_mime = sniff_mime(temp_path)
        if detected_mime not in allowed_mimes:
            raise UploadError(f"{label} content does not match the allowed MIME types.")

        temp_path.replace(final_path)
        return SavedUpload(
            filename=final_name,
            original_name=original_name,
            size=size,
            mime_type=detected_mime,
        )
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def delete_upload(directory: str | Path, filename: str | None) -> None:
    if not filename:
        return
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        return

    base = Path(directory).resolve()
    try:
        target = (base / filename).resolve(strict=False)
        target.relative_to(base)
    except ValueError:
        return

    if target.exists() and target.is_file():
        target.unlink(missing_ok=True)


def sniff_mime(path: str | Path) -> str:
    with Path(path).open("rb") as file_obj:
        header = file_obj.read(32)

    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith(b"BM"):
        return "image/bmp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "video/mp4"
    return "application/octet-stream"


def _cleanup_temp_dir(temp_dir: Path) -> None:
    if not temp_dir.exists():
        return
    for candidate in temp_dir.iterdir():
        if candidate.is_file() and candidate.suffix in {".part", ".upload"}:
            candidate.unlink(missing_ok=True)


def _path_value(value: object | None, fallback: Path) -> Path:
    if value is None:
        return Path(fallback)
    return Path(value).expanduser()


def _extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()
