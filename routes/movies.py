from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

import google_drive
from models import ADMIN_USERNAMES, Movie, db_session
from storage import storage_manager
from uploads import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIMES,
    ALLOWED_VIDEO_EXTENSIONS,
    ALLOWED_VIDEO_MIMES,
    StagedUpload,
    UploadError,
    stage_upload,
)


movies_bp = Blueprint("movies", __name__, url_prefix="/dashboard/movies")


@movies_bp.route("")
@movies_bp.route("/")
@login_required
def index():
    query_text = request.args.get("q", "").strip()
    query = db_session.query(Movie)
    if query_text:
        pattern = f"%{query_text}%"
        query = query.filter(or_(Movie.title.ilike(pattern), Movie.description.ilike(pattern)))
    movies = query.order_by(Movie.updated_at.desc(), Movie.id.desc()).all()
    return render_template("movies/index.html", movies=movies, q=query_text)


@movies_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    if not current_user.is_admin_role:
        abort(403)

    values = {"title": "", "description": ""}
    errors: list[str] = []

    if request.method == "POST":
        values, errors = _validate_movie_form()
        cover_file = request.files.get("cover")
        video_file = request.files.get("video")

        if not errors:
            staged_cover: StagedUpload | None = None
            staged_video: StagedUpload | None = None
            cover_file_id: str | None = None
            video_file_id: str | None = None
            account = None
            try:
                staged_cover = stage_upload(
                    cover_file,
                    allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                    allowed_mimes=ALLOWED_IMAGE_MIMES,
                    max_bytes=current_app.config["MAX_IMAGE_BYTES"],
                    label="Cover image",
                    temp_dir=current_app.config.get("UPLOAD_TMP_DIR"),
                )
                staged_video = stage_upload(
                    video_file,
                    allowed_extensions=ALLOWED_VIDEO_EXTENSIONS,
                    allowed_mimes=ALLOWED_VIDEO_MIMES,
                    max_bytes=current_app.config["MAX_VIDEO_BYTES"],
                    label="Movie video",
                    temp_dir=current_app.config.get("UPLOAD_TMP_DIR"),
                )
                account = storage_manager.next_account()
                cover_file_id = google_drive.upload_poster(
                    account,
                    staged_cover.temp_path,
                    staged_cover.mime_type,
                    account.posters_folder_id,
                    staged_cover.original_name,
                )
                video_file_id = google_drive.upload_video(
                    account,
                    staged_video.temp_path,
                    staged_video.mime_type,
                    account.videos_folder_id,
                    staged_video.original_name,
                )
                movie = Movie(
                    user_id=current_user.id,
                    title=values["title"],
                    description=values["description"],
                    cover_filename=cover_file_id,
                    cover_original_name=staged_cover.original_name,
                    cover_size=staged_cover.size,
                    drive_account_index=account.index,
                    video_filename=video_file_id,
                    video_original_name=staged_video.original_name,
                    video_size=staged_video.size,
                )
                db_session.add(movie)
                db_session.commit()
            except UploadError as exc:
                errors.append(str(exc))
            except google_drive.DriveError as exc:
                current_app.logger.exception("Google Drive error creating movie")
                if current_app.debug:
                    raise
                errors.append(str(exc))
            except SQLAlchemyError:
                db_session.rollback()
                if account is not None and cover_file_id:
                    google_drive.delete_file(account, cover_file_id)
                if account is not None and video_file_id:
                    google_drive.delete_file(account, video_file_id)
                errors.append("Movie could not be saved. Please try again.")
            finally:
                if staged_cover and staged_cover.temp_path.exists():
                    staged_cover.temp_path.unlink(missing_ok=True)
                if staged_video and staged_video.temp_path.exists():
                    staged_video.temp_path.unlink(missing_ok=True)

            if not errors:
                return _success_response("Movie created.")

        if _wants_json():
            return jsonify({"ok": False, "errors": errors}), 400

    return render_template(
        "movies/form.html",
        action="Create movie",
        errors=errors,
        values=values,
        movie=None,
    )


@movies_bp.route("/<int:movie_id>/edit", methods=["GET", "POST"])
@login_required
def edit(movie_id: int):
    movie = _movie_or_404(movie_id)
    values = {"title": movie.title, "description": movie.description}
    errors: list[str] = []

    if request.method == "POST":
        values, errors = _validate_movie_form()
        cover_file = request.files.get("cover")
        video_file = request.files.get("video")
        has_new_cover = bool(cover_file and cover_file.filename)
        has_new_video = bool(video_file and video_file.filename)

        if not errors:
            staged_cover: StagedUpload | None = None
            staged_video: StagedUpload | None = None
            new_cover_id: str | None = None
            new_video_id: str | None = None
            old_cover = movie.cover_filename
            old_video = movie.video_filename
            old_account_index = movie.drive_account_index
            try:
                current_account = storage_manager.get_account(movie.drive_account_index)

                if has_new_cover:
                    staged_cover = stage_upload(
                        cover_file,
                        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
                        allowed_mimes=ALLOWED_IMAGE_MIMES,
                        max_bytes=current_app.config["MAX_IMAGE_BYTES"],
                        label="Cover image",
                        temp_dir=current_app.config.get("UPLOAD_TMP_DIR"),
                    )
                    new_cover_id = google_drive.upload_poster(
                        current_account,
                        staged_cover.temp_path,
                        staged_cover.mime_type,
                        current_account.posters_folder_id,
                        staged_cover.original_name,
                    )
                    movie.cover_filename = new_cover_id
                    movie.cover_original_name = staged_cover.original_name
                    movie.cover_size = staged_cover.size
                    movie.drive_account_index = current_account.index

                if has_new_video:
                    staged_video = stage_upload(
                        video_file,
                        allowed_extensions=ALLOWED_VIDEO_EXTENSIONS,
                        allowed_mimes=ALLOWED_VIDEO_MIMES,
                        max_bytes=current_app.config["MAX_VIDEO_BYTES"],
                        label="Movie video",
                        temp_dir=current_app.config.get("UPLOAD_TMP_DIR"),
                    )
                    new_video_id = google_drive.upload_video(
                        current_account,
                        staged_video.temp_path,
                        staged_video.mime_type,
                        current_account.videos_folder_id,
                        staged_video.original_name,
                    )
                    movie.video_filename = new_video_id
                    movie.video_original_name = staged_video.original_name
                    movie.video_size = staged_video.size
                    movie.drive_account_index = current_account.index

                movie.title = values["title"]
                movie.description = values["description"]
                db_session.commit()
            except UploadError as exc:
                errors.append(str(exc))
            except google_drive.DriveError as exc:
                current_app.logger.exception("Google Drive error updating movie")
                errors.append(str(exc))
            except SQLAlchemyError:
                db_session.rollback()
                if new_cover_id and current_account is not None:
                    google_drive.delete_file(current_account, new_cover_id)
                if new_video_id and current_account is not None:
                    google_drive.delete_file(current_account, new_video_id)
                errors.append("Movie could not be updated. Please try again.")
            finally:
                if staged_cover and staged_cover.temp_path.exists():
                    staged_cover.temp_path.unlink(missing_ok=True)
                if staged_video and staged_video.temp_path.exists():
                    staged_video.temp_path.unlink(missing_ok=True)

            if not errors:
                if new_cover_id and old_cover:
                    old_account = storage_manager.get_account(old_account_index)
                    google_drive.delete_file(old_account, old_cover)
                if new_video_id and old_video:
                    old_account = storage_manager.get_account(old_account_index)
                    google_drive.delete_file(old_account, old_video)
                return _success_response("Movie updated.")

        if _wants_json():
            return jsonify({"ok": False, "errors": errors}), 400

    return render_template(
        "movies/form.html",
        action="Edit movie",
        errors=errors,
        values=values,
        movie=movie,
    )


@movies_bp.route("/<int:movie_id>/delete", methods=["POST"])
@login_required
def delete(movie_id: int):
    movie = _movie_or_404(movie_id)
    cover_filename = movie.cover_filename
    video_filename = movie.video_filename

    account = storage_manager.get_account(movie.drive_account_index)

    if cover_filename:
        if not google_drive.delete_file(account, cover_filename):
            flash("Movie cover could not be deleted from storage.", "error")
            return redirect(url_for("movies.index"))

    if video_filename:
        if not google_drive.delete_file(account, video_filename):
            flash("Movie video could not be deleted from storage.", "error")
            return redirect(url_for("movies.index"))

    db_session.delete(movie)
    try:
        db_session.commit()
    except SQLAlchemyError:
        db_session.rollback()
        flash("Movie could not be deleted.", "error")
    else:
        flash("Movie deleted.", "success")
    return redirect(url_for("movies.index"))


def _validate_movie_form() -> tuple[dict[str, str], list[str]]:
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
    elif len(description) > 3000:
        errors.append("Description must be 3000 characters or fewer.")

    return values, errors


def _movie_or_404(movie_id: int) -> Movie:
    movie = db_session.get(Movie, movie_id)
    if movie is None:
        abort(404)
    if movie.user_id == current_user.id:
        return movie
    if not current_user.is_admin_role:
        abort(404)
    if movie.owner and movie.owner.username in ADMIN_USERNAMES:
        abort(404)
    return movie


def _wants_json() -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _success_response(message: str):
    flash(message, "success")
    if _wants_json():
        return jsonify({"ok": True, "redirect": url_for("movies.index")})
    return redirect(url_for("movies.index"))
