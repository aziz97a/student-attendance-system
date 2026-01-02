from flask import Blueprint, request
from sqlalchemy import text
from ..extensions import db
from ..models.user import User, UserRole


health_bp = Blueprint("health", __name__)

@health_bp.post("/test/create-user")
def create_user():
    data = request.get_json() or {}
    user = User(
        full_name=data.get("full_name", "Test User"),
        email=data.get("email", "test@example.com"),
        role=UserRole.student,
    )
    user.set_password(data.get("password", "123456"))
    db.session.add(user)
    db.session.commit()
    return user.to_dict(), 201




@health_bp.get("/health")
def health():
    db.session.execute(text("SELECT 1"))
    return {"status": "ok", "db": "up"}

