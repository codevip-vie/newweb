from __future__ import annotations

import hmac
import re
import secrets
from urllib.parse import urlsplit

from flask import abort, request, session


CSRF_SESSION_KEY = "_csrf_token"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")


def generate_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(token: str | None) -> bool:
    expected = session.get(CSRF_SESSION_KEY)
    if not token or not expected:
        return False
    return hmac.compare_digest(str(expected), str(token))


def init_csrf(app) -> None:
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def csrf_protect() -> None:
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        token = request.form.get("_csrf_token") or request.headers.get("X-CSRFToken")
        if not validate_csrf_token(token):
            abort(400, description="Security token validation failed.")


def validate_username(username: str) -> str | None:
    if not username:
        return "Username is required."
    if not USERNAME_RE.fullmatch(username):
        return "Username must be 3-30 characters and use only letters, numbers, dots, hyphens, or underscores."
    return None


def validate_email(email: str) -> str | None:
    if not email:
        return "Email is required."
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        return "Enter a valid email address."
    return None


def validate_password(password: str) -> str | None:
    if not password:
        return "Password is required."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if len(password) > 128:
        return "Password must be 128 characters or fewer."
    if password.strip() != password:
        return "Password cannot begin or end with spaces."
    return None


def is_safe_redirect(target: str | None) -> bool:
    if not target:
        return False
    parsed = urlsplit(target)
    return parsed.scheme == "" and parsed.netloc == "" and target.startswith("/")
