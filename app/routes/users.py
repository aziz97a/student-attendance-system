from flask import Blueprint, request
from ..extensions import db
from ..models import User, UserRole

users_bp = Blueprint("users", __name__)

@users_bp.post("/users")
def create_user():
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "student").strip()

    if not full_name or not email or not password:
        return {"error": "full_name, email, password are required"}, 400

    try:
        role_enum = UserRole(role)
    except ValueError:
        return {"error": "role must be one of: admin, teacher, student"}, 400

    if User.query.filter_by(email=email).first():
        return {"error": "email already exists"}, 409

    user = User(full_name=full_name, email=email, role=role_enum)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return user.to_dict(), 201
