from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Iterable


DEFAULT_GOOGLE_OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", stripped)
        if not match:
            continue

        key, value = match.groups()
        if not key or key in os.environ:
            continue

        if value.startswith("\'") and value.endswith("\'"):
            value = value[1:-1]
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]

        os.environ[key] = value


_load_dotenv(Path(__file__).resolve().parent / ".env")


def _get_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_name(name: str, index: int) -> str:
    return f"{name}_{index}" if index and name else name


def _get_env(name: str, index: int, default: str | None = None) -> str | None:
    if index == 0:
        value = os.environ.get(name)
        if value is not None:
            return value
        return os.environ.get(_env_name(name, index), default)
    return os.environ.get(_env_name(name, index), default)


def _build_google_drive_storage_accounts(count: int) -> list[dict[str, str | None]]:
    accounts: list[dict[str, str | None]] = []
    for index in range(max(1, count)):
        accounts.append(
            {
                "index": index,
                "service_account": _get_env("GOOGLE_SERVICE_ACCOUNT", index),
                "oauth_client_id": _get_env("GOOGLE_OAUTH_CLIENT_ID", index),
                "oauth_client_secret": _get_env("GOOGLE_OAUTH_CLIENT_SECRET", index),
                "oauth_refresh_token": _get_env("GOOGLE_OAUTH_REFRESH_TOKEN", index),
                "oauth_token_file": _get_env("GOOGLE_OAUTH_TOKEN_FILE", index),
                "oauth_token_uri": _get_env("GOOGLE_OAUTH_TOKEN_URI", index, DEFAULT_GOOGLE_OAUTH_TOKEN_URI),
                "system_folder_id": _get_env("GOOGLE_DRIVE_SYSTEM_FOLDER_ID", index),
                "posters_folder_id": _get_env("GOOGLE_DRIVE_POSTERS_FOLDER_ID", index),
                "videos_folder_id": _get_env("GOOGLE_DRIVE_VIDEOS_FOLDER_ID", index),
            }
        )
    return accounts


class Config:
    BASE_DIR = Path(__file__).resolve().parent
    INSTANCE_DIR = BASE_DIR / "instance"

    SITE_NAME = os.environ.get("SITE_NAME", "Ani-BL")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-this-secret-key")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", INSTANCE_DIR / "movie_manager.sqlite3"))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{DATABASE_PATH.as_posix()}",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False},
    }

    UPLOAD_ROOT = Path(os.environ.get("UPLOAD_ROOT", INSTANCE_DIR / "uploads")).expanduser()
    UPLOAD_TMP_DIR = Path(os.environ.get("UPLOAD_TMP_DIR", UPLOAD_ROOT / ".tmp")).expanduser()
    POSTER_UPLOAD_DIR = UPLOAD_ROOT / "posters"
    MOVIE_COVER_UPLOAD_DIR = UPLOAD_ROOT / "movie_covers"
    MOVIE_VIDEO_UPLOAD_DIR = UPLOAD_ROOT / "movie_videos"
    FOUNDER_UPLOAD_DIR = UPLOAD_ROOT / "founder_images"
    AVATAR_UPLOAD_DIR = UPLOAD_ROOT / "avatars"
    CHAT_UPLOAD_DIR = UPLOAD_ROOT / "chat_attachments"

    MAX_IMAGE_BYTES = 8 * 1024 * 1024
    MAX_VIDEO_BYTES = 5 * 1024 * 1024 * 1024
    MAX_CONTENT_LENGTH = MAX_VIDEO_BYTES + (32 * 1024 * 1024)

    AUTHOR_NAME = os.environ.get("AUTHOR_NAME", "LeGiaHuy")
    AUTHOR_ROLE = os.environ.get("AUTHOR_ROLE", "CODE trưởng")
    AUTHOR_BIO = os.environ.get(
        "AUTHOR_BIO",
        "Tay dev chủ chốt.",
    )
    COFOUNDER_ONE_NAME = os.environ.get("COFOUNDER_ONE_NAME", "Đồng sáng lập: ChatGPT")
    COFOUNDER_ONE_ROLE = os.environ.get("COFOUNDER_ONE_ROLE", "sáng lập UX/UI")
    COFOUNDER_ONE_BIO = os.environ.get(
        "COFOUNDER_ONE_BIO",
        "Phụ trách định hướng poster, danh mục phim và trải nghiệm nội dung cho người xem.",
    )
    COFOUNDER_TWO_NAME = os.environ.get("COFOUNDER_TWO_NAME", "Đồng sáng lập: github copilot")
    COFOUNDER_TWO_ROLE = os.environ.get("COFOUNDER_TWO_ROLE", "sáng lập kỹ thuật")
    COFOUNDER_TWO_BIO = os.environ.get(
        "COFOUNDER_TWO_BIO",
        "Phụ trách vận hành nền tảng, bảo mật upload và trải nghiệm xem phim ổn định.",
    )
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin_password=3,141592653589793")

    GOOGLE_SERVICE_ACCOUNT = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
    GOOGLE_DRIVE_ACCOUNT_COUNT = _get_int_env("GOOGLE_DRIVE_ACCOUNT_COUNT", 1)
    GOOGLE_DRIVE_SYSTEM_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_SYSTEM_FOLDER_ID")
    GOOGLE_DRIVE_ACCOUNTS = _build_google_drive_storage_accounts(GOOGLE_DRIVE_ACCOUNT_COUNT)
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    GOOGLE_OAUTH_REFRESH_TOKEN = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")
    GOOGLE_OAUTH_TOKEN_FILE = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE")
    GOOGLE_OAUTH_TOKEN_URI = os.environ.get(
        "GOOGLE_OAUTH_TOKEN_URI", DEFAULT_GOOGLE_OAUTH_TOKEN_URI
    )
    GOOGLE_DRIVE_POSTERS_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_POSTERS_FOLDER_ID")
    GOOGLE_DRIVE_VIDEOS_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_VIDEOS_FOLDER_ID")
    GOOGLE_OAUTH_TOKEN_PATH = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE") or str(INSTANCE_DIR / "google_drive_oauth.json")
