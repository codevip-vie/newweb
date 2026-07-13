from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Flask, abort, render_template, url_for
from flask_login import LoginManager, current_user, logout_user
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from models import ADMIN_USERNAMES, Founder, User, db_session, init_db, init_engine
from routes import register_blueprints
from routes.media import founder_image_url, movie_cover_url, poster_image_url
from security import init_csrf
from storage import storage_manager
from uploads import ensure_upload_dirs
from backup import BackupManager


login_manager = LoginManager()


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    ensure_upload_dirs(app.config)
    storage_manager.initialize(app.config["GOOGLE_DRIVE_ACCOUNTS"])

    backup_manager = BackupManager(app)
    app.backup_manager = backup_manager
    # Restore from cloud backup before SQLAlchemy opens the local database.
    backup_manager.perform_startup_restore()

    init_engine(
        app.config["SQLALCHEMY_DATABASE_URI"],
        app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {}),
    )
    init_db()
    backup_manager.start_backup_thread()

    original_commit = db_session.commit

    def commit_with_backup(*args: object, **kwargs: object) -> object:
        result = original_commit(*args, **kwargs)
        try:
            backup_manager.mark_dirty()
        except Exception:
            pass
        return result

    db_session.commit = commit_with_backup

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "info"
    login_manager.init_app(app)

    init_csrf(app)
    register_blueprints(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        if not user_id.isdigit():
            return None
        user = db_session.get(User, int(user_id))
        if user is None or not user.is_active:
            return None
        return user

    @app.teardown_appcontext
    def shutdown_session(exception: BaseException | None = None) -> None:
        db_session.remove()

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        authors = []
        try:
            founders = db_session.query(Founder).order_by(Founder.id).all()
        except Exception:
            founders = []

        if founders:
            for founder in founders:
                if founder.image_filename:
                    image_url = founder_image_url(founder)
                    if image_url is None:
                        image_url = "img/author.svg"
                else:
                    image_url = "img/author.svg"
                authors.append(
                    {
                        "id": founder.id,
                        "name": founder.name,
                        "role": founder.role,
                        "bio": founder.bio,
                        "image": image_url,
                    }
                )
        else:
            authors = [
                {
                    "id": None,
                    "name": app.config["AUTHOR_NAME"],
                    "role": app.config["AUTHOR_ROLE"],
                    "bio": app.config["AUTHOR_BIO"],
                    "image": url_for("static", filename="img/author.svg"),
                },
                {
                    "id": None,
                    "name": app.config["COFOUNDER_ONE_NAME"],
                    "role": app.config["COFOUNDER_ONE_ROLE"],
                    "bio": app.config["COFOUNDER_ONE_BIO"],
                    "image": url_for("static", filename="img/author.svg"),
                },
                {
                    "id": None,
                    "name": app.config["COFOUNDER_TWO_NAME"],
                    "role": app.config["COFOUNDER_TWO_ROLE"],
                    "bio": app.config["COFOUNDER_TWO_BIO"],
                    "image": url_for("static", filename="img/author.svg"),
                },
            ]

        return {
            "site_name": app.config["SITE_NAME"],
            "current_year": datetime.utcnow().year,
            "author": authors[0],
            "authors": authors,
            "admin_usernames": ADMIN_USERNAMES,
            "poster_image_url": poster_image_url,
            "movie_cover_url": movie_cover_url,
            "founder_image_url": founder_image_url,
        }

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_upload(error: RequestEntityTooLarge):
        return (
            render_template(
                "error.html",
                title="Upload too large",
                message="The selected file exceeds the allowed upload size.",
            ),
            413,
        )

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def handle_error(error: HTTPException):
        code = getattr(error, "code", 500)
        title = getattr(error, "name", "Application error")
        if code == 500:
            title = "Something went wrong"
        return (
            render_template(
                "error.html",
                title=title,
                message=getattr(error, "description", "Please try again."),
            ),
            code,
        )

    @app.cli.command("init-db")
    def init_db_command() -> None:
        init_db()
        _ensure_default_admin(app)
        _ensure_default_founders(app)
        print("Database tables are ready.")

    _ensure_default_admin(app)
    _ensure_default_founders(app)

    return app


def _ensure_default_founders(app: Flask) -> None:
    existing_founders = db_session.query(Founder).count()
    if existing_founders > 0:
        return

    founders = [
        Founder(
            name=app.config["AUTHOR_NAME"],
            role=app.config["AUTHOR_ROLE"],
            bio=app.config["AUTHOR_BIO"],
        ),
        Founder(
            name=app.config["COFOUNDER_ONE_NAME"],
            role=app.config["COFOUNDER_ONE_ROLE"],
            bio=app.config["COFOUNDER_ONE_BIO"],
        ),
        Founder(
            name=app.config["COFOUNDER_TWO_NAME"],
            role=app.config["COFOUNDER_TWO_ROLE"],
            bio=app.config["COFOUNDER_TWO_BIO"],
        ),
    ]
    db_session.add_all(founders)
    try:
        db_session.commit()
    except Exception:
        db_session.rollback()


def _ensure_default_admin(app: Flask) -> None:
    admin_accounts = {
        "admin_default": "codeupperank@gmail.com",
        "admin_default_clone": "siuladzpro@gmail.com",
        "admin_default_third": "codeformypassion@gmail.com",
    }
    needs_commit = False

    for username, email in admin_accounts.items():
        user = db_session.query(User).filter(User.username == username).first()
        if user is None:
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(app.config["ADMIN_PASSWORD"]),
                is_admin=True,
                role="admin",
            )
            db_session.add(user)
            needs_commit = True
        else:
            if (
                not user.is_admin
                or user.role != "admin"
                or user.email != email
                or not user.is_active
                or not check_password_hash(user.password_hash, app.config["ADMIN_PASSWORD"])
            ):
                user.is_admin = True
                user.role = "admin"
                user.email = email
                user.is_active = True
                user.password_hash = generate_password_hash(app.config["ADMIN_PASSWORD"])
                needs_commit = True

    if needs_commit:
        try:
            db_session.commit()
        except Exception:
            db_session.rollback()


app = create_app()


if __name__ == "__main__":
    app.run()
