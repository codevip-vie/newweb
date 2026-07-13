from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from models import ADMIN_USERNAMES, User, db_session, utc_now
from security import is_safe_redirect, validate_email, validate_password, validate_username


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    values = {"username": "", "email": ""}
    errors: list[str] = []

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        values = {"username": username, "email": email}

        for validator_error in (
            validate_username(username),
            validate_email(email),
            validate_password(password),
        ):
            if validator_error:
                errors.append(validator_error)

        if password != confirm_password:
            errors.append("Password confirmation does not match.")

        if not errors:
            lower_username = username.lower()
            lower_email = email.lower()
            if lower_username in {name.lower() for name in ADMIN_USERNAMES}:
                errors.append("This username is reserved.")
            if lower_email in {"codeupperank@gmail.com", "siuladzpro@gmail.com"}:
                errors.append("This email is reserved.")

        if not errors:
            existing_user = (
                db_session.query(User)
                .filter(
                    or_(
                        func.lower(User.username) == username.lower(),
                        func.lower(User.email) == email,
                    )
                )
                .first()
            )
            if existing_user:
                if existing_user.username.lower() == username.lower():
                    errors.append("Username is already in use.")
                if existing_user.email.lower() == email:
                    errors.append("Email is already in use.")

        if not errors:
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
            )
            db_session.add(user)
            try:
                db_session.commit()
            except IntegrityError:
                db_session.rollback()
                errors.append("Username or email is already in use.")
            else:
                session.permanent = True
                login_user(user)
                flash("Your account is ready.", "success")
                return redirect(url_for("main.dashboard"))

    return render_template("auth/register.html", errors=errors, values=values)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    values = {"identifier": ""}
    errors: list[str] = []

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        values = {"identifier": identifier}

        if not identifier:
            errors.append("Username or email is required.")
        if not password:
            errors.append("Password is required.")

        user = None
        if not errors:
            lookup = identifier.lower()
            user = (
                db_session.query(User)
                .filter(or_(func.lower(User.username) == lookup, func.lower(User.email) == lookup))
                .first()
            )
            if user is None or not check_password_hash(user.password_hash, password):
                errors.append("Invalid username, email, or password.")
            elif not user.is_active:
                errors.append("This account has been banned.")

        if not errors and user:
            user.last_login_at = utc_now()
            db_session.commit()
            session.permanent = True
            login_user(user)
            flash("Welcome back.", "success")
            next_url = request.form.get("next") or request.args.get("next")
            return redirect(next_url if is_safe_redirect(next_url) else url_for("main.dashboard"))

    return render_template(
        "auth/login.html",
        errors=errors,
        values=values,
        next_url=request.args.get("next", ""),
    )


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.home"))
