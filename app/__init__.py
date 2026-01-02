from flask import Flask
from .config import Config
from .extensions import db, migrate , jwt

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    from flask_jwt_extended import JWTManager
    from .jwt_callbacks import is_token_revoked

    @jwt.token_in_blocklist_loader
    def token_in_blocklist_loader(jwt_header, jwt_payload):
      return is_token_revoked(jwt_header, jwt_payload)


    from . import models  # noqa: F401

    # # Register blueprints
    # from .routes.health import health_bp
    # app.register_blueprint(health_bp)

    from .routes import register_blueprints
    register_blueprints(app)


    @app.get("/routes")
    def show_routes():
     return {"routes": sorted([str(r) for r in app.url_map.iter_rules()])}


    return app
