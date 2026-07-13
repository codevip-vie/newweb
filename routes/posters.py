from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

import google_drive
from models import ADMIN_USERNAMES, Poster, db_session
from uploads import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIMES,
    StagedUpload,
    UploadError,
    stage_upload,
)
from storage import storage_manager

posters_bp = Blueprint("posters", __name__, url_prefix="/dashboard/posters")


@posters_bp.route("")
@posters_bp.route("/")
@login_required
def index():
    query_text = request.args.get("q", "").strip()
    query = db_session.query(Poster)
    if query_text:
        pattern = f"%{query_text}%"
        query = query.filter(or_(Poster.title.ilike(pattern), Poster.description.ilike(pattern)))
    posters = query.order_by(Poster.updated_at.desc(), Poster.id.desc()).all()
    return render_template("posters/index.html", posters=posters, q=query_text)


@posters_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if not current_user.is_admin_role:
        abort(403)

    values = {"title": "", "description": ""}
    errors: list[str] = []

    if request.method == "POST":
        values, errors = _validate_poster_form()
        image_file = request.files.get("image")

        if not errors:
            staged_image: StagedUpload | None = None
            file_id: str | None = None
            account = None
            try:
                staged_image = stage_upload(
                    image_file,
                    allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                    allowed_mimes=ALLOWED_IMAGE_MIMES,
                    max_bytes=current_app.config["MAX_IMAGE_BYTES"],
                    label="Poster image",
                    temp_dir=current_app.config.get("UPLOAD_TMP_DIR"),
                )
                account = storage_manager.next_account()
                file_id = google_drive.upload_poster(
                    account,
                    staged_image.temp_path,
                    staged_image.mime_type,
                    account.posters_folder_id,
                    staged_image.original_name,
                )
                poster = Poster(
                    user_id=current_user.id,
                    title=values["title"],
                    description=values["description"],
                    image_filename=file_id,
                    image_original_name=staged_image.original_name,
                    image_size=staged_image.size,
                    drive_account_index=account.index,
                )
                db_session.add(poster)
                db_session.commit()
            except UploadError as exc:
                errors.append(str(exc))
            except google_drive.DriveError as exc:
                current_app.logger.exception("Google Drive error creating poster")
                errors.append(str(exc))
            except SQLAlchemyError:
                db_session.rollback()
                if file_id and account is not None:
                    google_drive.delete_file(account, file_id)
                errors.append("Poster could not be saved. Please try again.")
            finally:
                if staged_image and staged_image.temp_path.exists():
                    staged_image.temp_path.unlink(missing_ok=True)

            if not errors:
                flash("Poster created.", "success")
                return redirect(url_for("posters.index"))

    return render_template(
        "posters/form.html",
        action="Create poster",
        errors=errors,
        values=values,
        poster=None,
    )


@posters_bp.route("/<int:poster_id>/edit", methods=["GET", "POST"])
@login_required
def edit(poster_id: int):
    poster = _owned_poster_or_404(poster_id)
    values = {"title": poster.title, "description": poster.description}
    errors: list[str] = []

    if request.method == "POST":
        values, errors = _validate_poster_form()
        image_file = request.files.get("image")
        has_new_image = bool(image_file and image_file.filename)

        if not errors:
            staged_image: StagedUpload | None = None
            new_file_id: str | None = None
            old_filename = poster.image_filename
            old_account_index = poster.drive_account_index
            try:
                if has_new_image:
                    staged_image = stage_upload(
                        image_file,
                        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                        allowed_mimes=ALLOWED_IMAGE_MIMES,
                        max_bytes=current_app.config["MAX_IMAGE_BYTES"],
                        label="Poster image",
                        temp_dir=current_app.config.get("UPLOAD_TMP_DIR"),
                    )
                    account = storage_manager.next_account()
                    new_file_id = google_drive.upload_poster(
                        account,
                        staged_image.temp_path,
                        staged_image.mime_type,
                        account.posters_folder_id,
                        staged_image.original_name,
                    )
                    poster.image_filename = new_file_id
                    poster.image_original_name = staged_image.original_name
                    poster.image_size = staged_image.size
                    poster.drive_account_index = account.index
                poster.title = values["title"]
                poster.description = values["description"]
                db_session.commit()
            except UploadError as exc:
                errors.append(str(exc))
            except google_drive.DriveError as exc:
                current_app.logger.exception("Google Drive error updating poster")
                errors.append(str(exc))
            except SQLAlchemyError:
                db_session.rollback()
                if new_file_id and account is not None:
                    google_drive.delete_file(account, new_file_id)
                errors.append("Poster could not be updated. Please try again.")
            finally:
                if staged_image and staged_image.temp_path.exists():
                    staged_image.temp_path.unlink(missing_ok=True)

            if not errors:
                if new_file_id and old_filename:
                    old_account = storage_manager.get_account(old_account_index)
                    google_drive.delete_file(old_account, old_filename)
                flash("Poster updated.", "success")
                return redirect(url_for("posters.index"))

    return render_template(
        "posters/form.html",
        action="Edit poster",
        errors=errors,
        values=values,
        poster=poster,
    )


@posters_bp.route("/<int:poster_id>/delete", methods=["POST"])
@login_required
def delete(poster_id: int):
    poster = _poster_or_404(poster_id)
    filename = poster.image_filename

    if filename:
        account = storage_manager.get_account(poster.drive_account_index)
        if not google_drive.delete_file(account, filename):
            flash("Poster could not be deleted from storage.", "error")
            return redirect(url_for("posters.index"))

    db_session.delete(poster)
    try:
        db_session.commit()
    except SQLAlchemyError:
        db_session.rollback()
        flash("Poster could not be deleted.", "error")
    else:
        flash("Poster deleted.", "success")
    return redirect(url_for("posters.index"))


def _validate_poster_form() -> tuple[dict[str, str], list[str]]:
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    values = {"title": title, "description": description}
    errors: list[str] = []

    if not title:
        errors.append("Title is required.")
    elif len(title) > 140:
        errors.append("Title must be 140 characters or fewer.")

    if not description:
        errors.append("Description is required.")
    elif len(description) > 1200:
        errors.append("Description must be 1200 characters or fewer.")

    return values, errors


def _poster_or_404(poster_id: int) -> Poster:
    poster = db_session.get(Poster, poster_id)
    if poster is None:
        abort(404)
    if poster.user_id == current_user.id:
        return poster
    if not current_user.is_admin_role:
        abort(404)
    if poster.owner and poster.owner.username in ADMIN_USERNAMES:
        abort(404)
    return poster
