from .auth import auth_bp
from .health import health_bp
from .users import users_bp
from .courses import courses_bp


def register_blueprints(app):
    ...
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(users_bp, url_prefix="/api")
    app.register_blueprint(courses_bp, url_prefix="/api")

    