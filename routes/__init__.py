from __future__ import annotations


def register_blueprints(app) -> None:
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.media import media_bp
    from routes.movies import movies_bp
    from routes.posters import posters_bp
    from routes.features import features_bp
    from routes.dashboard_extra import extra_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(posters_bp)
    app.register_blueprint(movies_bp)
    app.register_blueprint(features_bp)
    app.register_blueprint(extra_bp)
    app.register_blueprint(media_bp)
