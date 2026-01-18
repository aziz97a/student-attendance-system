from .auth import auth_bp
from .health import health_bp
from .users import users_bp
from .courses import courses_bp
from .bulk_import import bulk_bp
from .attendance import attendance_bp
from .sessions import sessions_bp

def register_blueprints(app):
    ...
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix="/api")
    app.register_blueprint(users_bp, url_prefix="/api")
    app.register_blueprint(courses_bp, url_prefix="/api")
    app.register_blueprint(bulk_bp, url_prefix="/api")
    app.register_blueprint(sessions_bp, url_prefix="/api")
    app.register_blueprint(attendance_bp, url_prefix="/api")


    