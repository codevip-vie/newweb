from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

import google_drive
from models import ADMIN_USERNAMES, Founder, Movie, MovieComment, Poster, PosterComment, User, db_session
from security import validate_email, validate_password, validate_username
from storage import storage_manager
from uploads import (
    ALLOWED_IMAGE_EXTENSIONS_ALL,
    ALLOWED_IMAGE_MIMES_ALL,
    StagedUpload,
    UploadError,
    stage_upload,
)


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    posters = (
        db_session.query(Poster)
        .order_by(Poster.updated_at.desc(), Poster.id.desc())
        .limit(6)
        .all()
    )
    movies = (
        db_session.query(Movie)
        .order_by(Movie.updated_at.desc(), Movie.id.desc())
        .limit(8)
        .all()
    )
    hero_movies = movies[:3]
    hero_posters = posters[:3] if not hero_movies else []
    return render_template(
        "home.html",
        posters=posters,
        movies=movies,
        hero_movies=hero_movies,
        hero_posters=hero_posters,
    )


@main_bp.route("/dashboard")
@login_required
def dashboard():
    poster_count = (
        db_session.query(func.count(Poster.id))
        .filter(Poster.user_id == current_user.id)
        .scalar()
    )
    movie_count = (
        db_session.query(func.count(Movie.id))
        .filter(Movie.user_id == current_user.id)
        .scalar()
    )
    latest_posters = (
        db_session.query(Poster)
        .filter(Poster.user_id == current_user.id)
        .order_by(Poster.updated_at.desc())
        .limit(3)
        .all()
    )
    latest_movies = (
        db_session.query(Movie)
        .filter(Movie.user_id == current_user.id)
        .order_by(Movie.updated_at.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "dashboard/index.html",
        poster_count=poster_count,
        movie_count=movie_count,
        latest_posters=latest_posters,
        latest_movies=latest_movies,
    )


@main_bp.route("/dashboard/profile", methods=["GET", "POST"])
@login_required
def profile():
    values = {"username": current_user.username, "email": current_user.email}
    errors: list[str] = []

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        values = {"username": username, "email": email}

        for validator_error in (validate_username(username), validate_email(email)):
            if validator_error:
                errors.append(validator_error)

        duplicate_user = (
            db_session.query(User)
            .filter(
                User.id != current_user.id,
                or_(
                    func.lower(User.username) == username.lower(),
                    func.lower(User.email) == email,
                ),
            )
            .first()
        )
        if duplicate_user:
            if duplicate_user.username.lower() == username.lower():
                errors.append("Username is already in use.")
            if duplicate_user.email.lower() == email:
                errors.append("Email is already in use.")

        if not errors:
            if username.lower() in {name.lower() for name in ADMIN_USERNAMES}:
                errors.append("This username is reserved.")
            if email.lower() in {"codeupperank@gmail.com", "siuladzpro@gmail.com"}:
                errors.append("This email is reserved.")
            if current_user.username in ADMIN_USERNAMES:
                if username != current_user.username:
                    errors.append("The admin account username cannot be changed.")
                if email != current_user.email:
                    errors.append("The admin account email cannot be changed.")

        changing_password = bool(current_password or new_password or confirm_password)
        if changing_password:
            if not check_password_hash(current_user.password_hash, current_password):
                errors.append("Current password is incorrect.")
            password_error = validate_password(new_password)
            if password_error:
                errors.append(password_error)
            if new_password != confirm_password:
                errors.append("New password confirmation does not match.")

        if not errors:
            current_user.username = username
            current_user.email = email
            if changing_password:
                current_user.password_hash = generate_password_hash(new_password)
            try:
                db_session.commit()
            except IntegrityError:
                db_session.rollback()
                errors.append("Username or email is already in use.")
            else:
                flash("Profile updated.", "success")
                return redirect(url_for("main.profile"))

    return render_template("dashboard/profile.html", errors=errors, values=values)


@main_bp.route("/dashboard/account/delete", methods=["POST"])
@login_required
def delete_account():
    if current_user.username in ADMIN_USERNAMES:
        abort(403)

    try:
        db_session.delete(current_user)
        db_session.commit()
    except SQLAlchemyError:
        db_session.rollback()
        flash("Your account could not be deleted. Please try again.", "error")
        return redirect(url_for("main.profile"))

    logout_user()
    flash("Your account has been deleted.", "success")
    return redirect(url_for("main.home"))


@main_bp.route("/dashboard/google-oauth/authorize")
@login_required
def google_drive_oauth_authorize():
    if not current_user.is_admin_role:
        abort(403)

    account_index = 0
    account_value = request.args.get("account")
    if account_value is not None:
        try:
            account_index = int(account_value)
        except ValueError:
            flash("Invalid account selection for Google OAuth.", "error")
            return redirect(url_for("main.dashboard"))

    if account_index < 0 or account_index >= len(storage_manager._accounts):
        flash("Requested Google Drive account is not configured.", "error")
        return redirect(url_for("main.dashboard"))

    account = storage_manager._accounts[account_index]

    redirect_uri = url_for("main.google_drive_oauth_callback", _external=True)
    try:
        authorization_url = google_drive.get_oauth_authorization_url(
            redirect_uri, state=str(account_index), account=account
        )
    except google_drive.DriveError as exc:
        current_app.logger.exception("Google OAuth authorize route failed")
        if current_app.debug:
            raise
        flash(str(exc), "error")
        return redirect(url_for("main.dashboard"))

    return redirect(authorization_url)


@main_bp.route("/dashboard/google-oauth/callback")
@login_required
def google_drive_oauth_callback():
    if not current_user.is_admin_role:
        abort(403)

    error = request.args.get("error")
    if error:
        flash(f"Google OAuth error: {error}", "error")
        return redirect(url_for("main.dashboard"))

    code = request.args.get("code")
    if not code:
        flash("Google OAuth authorization code is missing.", "error")
        return redirect(url_for("main.dashboard"))

    account_index = 0
    state = request.args.get("state")
    if state is not None:
        try:
            account_index = int(state)
        except ValueError:
            flash("Invalid OAuth callback state received.", "error")
            return redirect(url_for("main.dashboard"))

    if account_index < 0 or account_index >= len(storage_manager._accounts):
        flash("OAuth callback account index is invalid.", "error")
        return redirect(url_for("main.dashboard"))

    account = storage_manager._accounts[account_index]

    redirect_uri = url_for("main.google_drive_oauth_callback", _external=True)
    try:
        google_drive.exchange_authorization_code(code, redirect_uri, account=account)
    except google_drive.DriveError as exc:
        current_app.logger.exception("Google OAuth callback failed")
        if current_app.debug:
            raise
        flash(str(exc), "error")
        return redirect(url_for("main.dashboard"))

    if account is not None:
        flash(
            f"Google Drive authorization completed for account {account.index}. Refresh token saved.",
            "success",
        )
    else:
        flash("Google Drive authorization completed. Refresh token saved.", "success")
    return redirect(url_for("main.google_drive_oauth_status"))


@main_bp.route("/dashboard/google-oauth/status")
@login_required
def google_drive_oauth_status():
    if not current_user.is_admin_role:
        abort(403)

    account_list = []
    for account in storage_manager._accounts:
        account_list.append(
            {
                "index": account.index,
                "oauth_configured": bool(account.oauth_client_id and account.oauth_client_secret),
                "refresh_token_available": google_drive.has_refresh_token(account),
                "posters_folder_configured": bool(account.posters_folder_id),
                "videos_folder_configured": bool(account.videos_folder_id),
                "authorize_url": url_for(
                    "main.google_drive_oauth_authorize", account=account.index
                ),
            }
        )

    if not account_list:
        flash("No Google Drive accounts are configured.", "error")
        return redirect(url_for("main.dashboard"))

    return render_template("dashboard/google_oauth_status.html", accounts=account_list)


@main_bp.route("/dashboard/backup-status")
@login_required
def backup_status():
    if not current_user.is_admin_role:
        abort(403)

    backup_manager = getattr(current_app, "backup_manager", None)
    if backup_manager is None:
        flash("Backup manager is not available.", "error")
        return redirect(url_for("main.dashboard"))

    return render_template(
        "dashboard/backup_status.html",
        backup_status={
            "last_backup_status": backup_manager.last_backup_status,
            "last_backup_time": backup_manager.last_backup_time,
            "last_backup_message": backup_manager.last_backup_message,
            "last_restore_status": backup_manager.last_restore_status,
            "last_restore_time": backup_manager.last_restore_time,
            "last_restore_message": backup_manager.last_restore_message,
        },
    )


@main_bp.route("/dashboard/backup-status/trigger", methods=["POST"])
@login_required
def backup_trigger():
    if not current_user.is_admin_role:
        abort(403)

    backup_manager = getattr(current_app, "backup_manager", None)
    if backup_manager is None:
        flash("Backup manager is not available.", "error")
        return redirect(url_for("main.backup_status"))

    success = backup_manager.create_backup_now()
    if success:
        flash("Backup completed successfully.", "success")
    else:
        flash("Backup failed. Check the backup status panel for details.", "error")

    return redirect(url_for("main.backup_status"))


@main_bp.route("/dashboard/users")
@login_required
def users():
    if not current_user.is_admin_role:
        abort(403)

    users = db_session.query(User).order_by(User.username).all()
    return render_template("dashboard/users.html", users=users)


@main_bp.route("/dashboard/users/<int:user_id>/ban", methods=["POST"])
@login_required
def ban_user(user_id: int):
    if not current_user.is_admin_role:
        abort(403)
    if current_user.id == user_id:
        abort(403)

    user = db_session.get(User, user_id)
    if user is None:
        abort(404)
    if user.is_admin_role:
        abort(403)

    user.is_active = False
    try:
        db_session.commit()
    except SQLAlchemyError:
        db_session.rollback()
        flash("Unable to ban the selected user.", "error")
        return redirect(url_for("main.users"))

    flash("User has been banned.", "success")
    return redirect(url_for("main.users"))


@main_bp.route("/dashboard/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id: int):
    if not current_user.is_admin_role:
        abort(403)
    if current_user.id == user_id:
        abort(403)

    user = db_session.get(User, user_id)
    if user is None:
        abort(404)
    if user.is_admin_role:
        abort(403)

    try:
        db_session.delete(user)
        db_session.commit()
    except SQLAlchemyError:
        db_session.rollback()
        flash("Unable to delete the selected user.", "error")
        return redirect(url_for("main.users"))

    flash("User account deleted.", "success")
    return redirect(url_for("main.users"))


@main_bp.route("/dashboard/founders")
@login_required
def founders():
    if not current_user.is_admin_role:
        abort(403)

    founders = db_session.query(Founder).order_by(Founder.id).all()
    return render_template("dashboard/founders.html", founders=founders)


@main_bp.route("/dashboard/founders/<int:founder_id>", methods=["POST"])
@login_required
def update_founder(founder_id: int):
    if not current_user.is_admin_role:
        abort(403)

    founder = db_session.get(Founder, founder_id)
    if founder is None:
        abort(404)

    bio = request.form.get("bio", "").strip()
    if not bio:
        flash("Founder description cannot be empty.", "error")
        return redirect(url_for("main.founders"))

    image_file = request.files.get("image")
    staged_image: StagedUpload | None = None
    new_image_id: str | None = None
    old_filename = founder.image_filename

    if image_file and image_file.filename:
        old_account_index = founder.drive_account_index
        try:
            staged_image = stage_upload(
                image_file,
                allowed_extensions=ALLOWED_IMAGE_EXTENSIONS_ALL,
                allowed_mimes=ALLOWED_IMAGE_MIMES_ALL,
                max_bytes=current_app.config["MAX_IMAGE_BYTES"],
                label="Founder avatar",
                temp_dir=current_app.config.get("UPLOAD_TMP_DIR"),
            )
            account = storage_manager.next_account()
            new_image_id = google_drive.upload_poster(
                account,
                staged_image.temp_path,
                staged_image.mime_type,
                account.posters_folder_id,
                staged_image.original_name,
            )
            founder.image_filename = new_image_id
            founder.image_original_name = staged_image.original_name
            founder.image_size = staged_image.size
            founder.drive_account_index = account.index
        except UploadError as exc:
            flash(str(exc), "error")
            return redirect(url_for("main.founders"))
        except google_drive.DriveError as exc:
            current_app.logger.exception("Founder avatar upload failed")
            flash(str(exc), "error")
            return redirect(url_for("main.founders"))
        except SQLAlchemyError:
            db_session.rollback()
            if new_image_id and google_drive.is_drive_file_id(new_image_id):
                google_drive.delete_file(account, new_image_id)
            flash("Founder information could not be updated.", "error")
            return redirect(url_for("main.founders"))
        finally:
            if staged_image and staged_image.temp_path.exists():
                staged_image.temp_path.unlink(missing_ok=True)

    founder.bio = bio
    try:
        db_session.commit()
    except SQLAlchemyError:
        db_session.rollback()
        if new_image_id and google_drive.is_drive_file_id(new_image_id):
            google_drive.delete_file(account, new_image_id)
        flash("Founder information could not be updated.", "error")
        return redirect(url_for("main.founders"))

    if new_image_id and old_filename and google_drive.is_drive_file_id(old_filename):
        old_account = storage_manager.get_account(old_account_index)
        google_drive.delete_file(old_account, old_filename)

    flash("Founder profile updated.", "success")
    return redirect(url_for("main.founders"))


@main_bp.route("/posters/<int:poster_id>")
def poster_detail(poster_id: int):
    poster = db_session.get(Poster, poster_id)
    if poster is None:
        abort(404)
    return render_template("posters/detail.html", poster=poster)


@main_bp.route("/posters/<int:poster_id>/comment", methods=["POST"])
@login_required
def poster_comment(poster_id: int):
    poster = db_session.get(Poster, poster_id)
    if poster is None:
        abort(404)

    body = request.form.get("body", "").strip()
    if not body:
        flash("Bình luận không được để trống.", "error")
        return redirect(url_for("main.poster_detail", poster_id=poster.id))

    comment = PosterComment(poster_id=poster.id, user_id=current_user.id, body=body)
    db_session.add(comment)
    try:
        db_session.commit()
        flash("Bình luận đã được gửi.", "success")
    except Exception:
        db_session.rollback()
        flash("Không thể lưu bình luận. Vui lòng thử lại.", "error")

    return redirect(url_for("main.poster_detail", poster_id=poster.id))


@main_bp.route("/movies/<int:movie_id>/watch")
@login_required
def watch_movie(movie_id: int):
    movie = db_session.get(Movie, movie_id)
    if movie is None:
        abort(404)
    return render_template("movies/watch.html", movie=movie)


@main_bp.route("/movies/<int:movie_id>/comment", methods=["POST"])
@login_required
def movie_comment(movie_id: int):
    movie = db_session.get(Movie, movie_id)
    if movie is None:
        abort(404)

    body = request.form.get("body", "").strip()
    if not body:
        flash("Bình luận không được để trống.", "error")
        return redirect(url_for("main.watch_movie", movie_id=movie.id))

    comment = MovieComment(movie_id=movie.id, user_id=current_user.id, body=body)
    db_session.add(comment)
    try:
        db_session.commit()
        flash("Bình luận đã được gửi.", "success")
    except Exception:
        db_session.rollback()
        flash("Không thể lưu bình luận. Vui lòng thử lại.", "error")

    return redirect(url_for("main.watch_movie", movie_id=movie.id))
