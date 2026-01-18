from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required, get_jwt
from psycopg2 import IntegrityError

from ..extensions import db
from ..models import User, UserRole, Student, Teacher

users_bp = Blueprint("users", __name__)


@users_bp.post("/users")
@jwt_required(optional=True)
def create_user():
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "").strip()

    if not full_name or not email or not password or not role:
        return {"error": "full_name, email, password, role are required"}, 400

    # Role validation
    try:
        role_enum = UserRole(role)
    except ValueError:
        return {"error": "role must be one of: admin, teacher, student"}, 400

    # Check caller role (if any token provided)
    claims = get_jwt() or {}
    caller_role = claims.get("role")  # None if no JWT

    # ✅ If NOT admin, restrict self-registration to student/teacher only
    if caller_role != UserRole.admin.value:
        if role_enum == UserRole.admin:
            return {"error": "cannot create admin without admin permission"}, 403
        if role_enum not in (UserRole.student, UserRole.teacher):
            return {"error": "role must be student or teacher"}, 400

    # Prevent duplicate email
    if User.query.filter_by(email=email).first():
        return {"error": "email already exists"}, 409

    # Create user
    user = User(full_name=full_name, email=email, role=role_enum)
    user.set_password(password)

    db.session.add(user)
    db.session.flush()  # get user.id before commit

    # Auto-create profile
    if role_enum == UserRole.student:
        db.session.add(Student(user_id=user.id))
    elif role_enum == UserRole.teacher:
        db.session.add(Teacher(user_id=user.id))

    db.session.commit()

    return user.to_dict(), 201


@users_bp.get("/users/me")
@jwt_required()
def get_me():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)
    return user.to_dict(), 200


@users_bp.put("/users/me")
@jwt_required()
def update_me():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()

    if not full_name:
        return {"error": "full_name is required"}, 400

    user.full_name = full_name
    db.session.commit()
    return user.to_dict(), 200



@users_bp.put("/users/me/password")
@jwt_required()
def change_my_password():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    if not current_password or not new_password:
        return {"error": "current_password and new_password are required"}, 400

    if len(new_password) < 6:
        return {"error": "new_password must be at least 6 characters"}, 400

    if not user.check_password(current_password):
        return {"error": "current_password is incorrect"}, 401

    user.set_password(new_password)
    user.must_change_password = False

    db.session.commit()
    return {"message": "password updated successfully"}, 200


@users_bp.delete("/users/me")
@jwt_required()
def delete_my_account():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""

    if not password:
        return {"error": "password is required"}, 400

    if not user.check_password(password):
        return {"error": "password is incorrect"}, 401

    try:
        db.session.delete(user)
        db.session.commit()
        return {"message": "account deleted"}, 200

    except IntegrityError:
        db.session.rollback()
        # Most likely: teacher owns courses (teacher_id has RESTRICT)
        return {
            "error": "cannot delete account due to related data (e.g., courses owned). "
                     "Delete/transfer related records first."
        }, 409
    

@users_bp.get("/students/me")
@jwt_required()
def get_student_profile_me():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    if user.role != UserRole.student:
        return {"error": "forbidden (student only)"}, 403

    profile = Student.query.get(user_id)  # PK = user_id
    if not profile:
        return {"error": "student profile not found"}, 404

    return profile.to_dict(), 200


@users_bp.put("/students/me")
@jwt_required()
def set_student_profile_me():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    if user.role != UserRole.student:
        return {"error": "forbidden (student only)"}, 403

    data = request.get_json(silent=True) or {}

    student_no = (data.get("student_no") or "").strip() or None
    department = (data.get("department") or "").strip() or None
    year_level = data.get("year_level", None)

    if year_level is not None:
        try:
            year_level = int(year_level)
        except (TypeError, ValueError):
            return {"error": "year_level must be an integer"}, 400

    profile = Student.query.get(user_id)
    if not profile:
        profile = Student(user_id=user_id)
        db.session.add(profile)

    # Unique checks (only if provided)
    if student_no:
        existing = Student.query.filter(Student.student_no == student_no, Student.user_id != user_id).first()
        if existing:
            return {"error": "student_no already exists"}, 409

    profile.student_no = student_no
    profile.department = department
    profile.year_level = year_level

    db.session.commit()
    return profile.to_dict(), 200





@users_bp.get("/teachers/me")
@jwt_required()
def get_teacher_profile_me():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    if user.role != UserRole.teacher:
        return {"error": "forbidden (teacher only)"}, 403

    profile = Teacher.query.get(user_id)  # PK = user_id
    if not profile:
        return {"error": "teacher profile not found"}, 404

    return profile.to_dict(), 200


@users_bp.put("/teachers/me")
@jwt_required()
def set_teacher_profile_me():
    user_id = int(get_jwt_identity())
    user = User.query.get_or_404(user_id)

    if user.role != UserRole.teacher:
        return {"error": "forbidden (teacher only)"}, 403

    data = request.get_json(silent=True) or {}

    staff_no = (data.get("staff_no") or "").strip() or None
    title = (data.get("title") or "").strip() or None

    profile = Teacher.query.get(user_id)
    if not profile:
        profile = Teacher(user_id=user_id)
        db.session.add(profile)

    # Unique checks (only if provided)
    if staff_no:
        existing = Teacher.query.filter(Teacher.staff_no == staff_no, Teacher.user_id != user_id).first()
        if existing:
            return {"error": "staff_no already exists"}, 409

    profile.staff_no = staff_no
    profile.title = title

    db.session.commit()
    return profile.to_dict(), 200


