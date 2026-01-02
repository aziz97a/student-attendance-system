from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt,
    get_jwt_identity,
)
from ..extensions import db
from ..models import User, TokenBlocklist

auth_bp = Blueprint("auth", __name__)

@auth_bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return {"error": "email and password are required"}, 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return {"error": "invalid credentials"}, 401

    if not user.is_active:
        return {"error": "account disabled"}, 403

    # identity should be simple (string/int). Keep it the user id.
    access_token = create_access_token(identity=str(user.id), additional_claims={"role": user.role.value})
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims={"role": user.role.value})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict(),
    }, 200


@auth_bp.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()  # string
    # create a new access token
    # include role again from current refresh token claims
    claims = get_jwt()
    role = claims.get("role")

    new_access = create_access_token(identity=user_id, additional_claims={"role": role})
    return {"access_token": new_access}, 200


@auth_bp.post("/auth/logout")
@jwt_required()  # logout access token
def logout_access():
    jti = get_jwt()["jti"]
    db.session.add(TokenBlocklist(jti=jti, token_type="access"))
    db.session.commit()
    return {"message": "access token revoked"}, 200


@auth_bp.post("/auth/logout-refresh")
@jwt_required(refresh=True)  # logout refresh token
def logout_refresh():
    jti = get_jwt()["jti"]
    db.session.add(TokenBlocklist(jti=jti, token_type="refresh"))
    db.session.commit()
    return {"message": "refresh token revoked"}, 200
