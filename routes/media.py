from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, url_for
from flask_login import login_required

import google_drive
from models import Founder, Movie, Poster, db_session


media_bp = Blueprint("media", __name__, url_prefix="/media")


def _resolve_drive_file_id(value: str | None) -> str | None:
    if not value:
        return None
    return google_drive.get_file_id(value)


def _migrate_poster_file_id(poster: Poster) -> str | None:
    file_id = _resolve_drive_file_id(poster.image_filename)
    if google_drive.is_drive_file_id(file_id):
        return file_id

    file_id = google_drive.search_file_id_by_name(
        current_app.config["GOOGLE_SERVICE_ACCOUNT"],
        poster.image_original_name or poster.image_filename,
        folder_id=current_app.config.get("GOOGLE_DRIVE_POSTERS_FOLDER_ID"),
        mime_type_prefix="image/",
        size=poster.image_size,
    )
    if file_id:
        poster.image_filename = file_id
        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
    return file_id


def _migrate_movie_cover_file_id(movie: Movie) -> str | None:
    file_id = _resolve_drive_file_id(movie.cover_filename)
    if google_drive.is_drive_file_id(file_id):
        return file_id

    file_id = google_drive.search_file_id_by_name(
        current_app.config["GOOGLE_SERVICE_ACCOUNT"],
        movie.cover_original_name or movie.cover_filename,
        folder_id=current_app.config.get("GOOGLE_DRIVE_POSTERS_FOLDER_ID"),
        mime_type_prefix="image/",
        size=movie.cover_size,
    )
    if file_id:
        movie.cover_filename = file_id
        try:
            db_session.commit()
        except Exception:
            db_session.rollback()
    return file_id


def _save_file_id(model: object, attr_name: str, file_id: str) -> None:
    if getattr(model, attr_name, None) != file_id:
        setattr(model, attr_name, file_id)
        try:
            db_session.commit()
        except Exception:
            db_session.rollback()


def _migrate_founder_image_file_id(founder: Founder) -> str | None:
    file_id = _resolve_drive_file_id(founder.image_filename)
    if google_drive.is_drive_file_id(file_id):
        _save_file_id(founder, "image_filename", file_id)
        return file_id

    file_id = google_drive.search_file_id_by_name(
        current_app.config["GOOGLE_SERVICE_ACCOUNT"],
        Path(founder.image_filename or "").name,
        folder_id=current_app.config.get("GOOGLE_DRIVE_POSTERS_FOLDER_ID"),
        mime_type_prefix="image/",
    )
    if file_id:
        _save_file_id(founder, "image_filename", file_id)
    return file_id


def _build_google_drive_image_url(file_id: str) -> str:
    return google_drive.build_google_drive_image_url(file_id)


def founder_image_url(founder: Founder | str | None) -> str | None:
    if isinstance(founder, Founder):
        file_id = _migrate_founder_image_file_id(founder)
        if google_drive.is_drive_file_id(file_id):
            return _build_google_drive_image_url(file_id)
        if founder.image_filename:
            return url_for("media.founder_image", filename=founder.image_filename)
        return None

    file_id = _resolve_drive_file_id(founder)
    if google_drive.is_drive_file_id(file_id):
        return _build_google_drive_image_url(file_id)
    return url_for("media.founder_image", filename=founder) if founder else None


def poster_image_url(poster: Poster) -> str | None:
    file_id = _migrate_poster_file_id(poster)
    if google_drive.is_drive_file_id(file_id):
        return _build_google_drive_image_url(file_id)
    return url_for("media.poster_image", filename=poster.image_filename)


def movie_cover_url(movie: Movie) -> str | None:
    file_id = _migrate_movie_cover_file_id(movie)
    if google_drive.is_drive_file_id(file_id):
        return _build_google_drive_image_url(file_id)
    return url_for("media.movie_cover", movie_id=movie.id)


@media_bp.route("/founders/<path:filename>")
def founder_image(filename: str):
    file_id = _resolve_drive_file_id(filename)
    if not google_drive.is_drive_file_id(file_id):
        abort(404)
    return redirect(_build_google_drive_image_url(file_id))


@media_bp.route("/posters/<path:filename>")
def poster_image(filename: str):
    poster = db_session.query(Poster).filter(Poster.image_filename == filename).first()
    if poster is None:
        abort(404)
    file_id = _migrate_poster_file_id(poster)
    if not google_drive.is_drive_file_id(file_id):
        abort(404)
    return redirect(_build_google_drive_image_url(file_id))


@media_bp.route("/posters/<int:poster_id>/download")
def poster_image_download(poster_id: int):
    poster = db_session.get(Poster, poster_id)
    if poster is None:
        abort(404)
    file_id = _migrate_poster_file_id(poster)
    if not google_drive.is_drive_file_id(file_id):
        abort(404)
    return redirect(google_drive.get_file_url(file_id))


@media_bp.route("/movies/<int:movie_id>/cover")
def movie_cover(movie_id: int):
    movie = db_session.get(Movie, movie_id)
    if movie is None:
        abort(404)
    file_id = _migrate_movie_cover_file_id(movie)
    if not google_drive.is_drive_file_id(file_id):
        abort(404)
    return redirect(_build_google_drive_image_url(file_id))


@media_bp.route("/movies/<int:movie_id>/video")
@login_required
def movie_video(movie_id: int):
    movie = db_session.get(Movie, movie_id)
    if movie is None:
        abort(404)
    file_id = _resolve_drive_file_id(movie.video_filename)
    if not google_drive.is_drive_file_id(file_id):
        abort(404)
    return redirect(google_drive.get_file_url(file_id))
