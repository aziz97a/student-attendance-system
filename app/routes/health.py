from flask import Blueprint
from sqlalchemy import text
from ..extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    db.session.execute(text("SELECT 1"))
    return {"status": "ok", "db": "up"}

