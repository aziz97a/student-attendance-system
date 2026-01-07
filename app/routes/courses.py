from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from ..extensions import db
from ..models import Course, Enrollment, UserRole

courses_bp = Blueprint("courses", __name__)


def _role_and_user_id():
    claims = get_jwt()
    role = claims.get("role")
    user_id = int(get_jwt_identity())
    return role, user_id


@courses_bp.post("/courses")
@jwt_required()
def create_course():
    role, user_id = _role_and_user_id()

    if role not in (UserRole.admin.value, UserRole.teacher.value):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    semester = (data.get("semester") or "").strip() or None

    if not code or not name:
        return {"error": "code and name are required"}, 400

    # who owns the course?
    if role == UserRole.teacher.value:
        teacher_id = user_id
    else:
        # admin can assign any teacher
        teacher_id = data.get("teacher_id")
        if not teacher_id:
            return {"error": "teacher_id is required for admin"}, 400
        try:
            teacher_id = int(teacher_id)
        except ValueError:
            return {"error": "teacher_id must be an integer"}, 400

    if Course.query.filter_by(code=code).first():
        return {"error": "course code already exists"}, 409

    course = Course(code=code, name=name, semester=semester, teacher_id=teacher_id)
    db.session.add(course)
    db.session.commit()

    return course.to_dict(), 201


@courses_bp.get("/courses")
@jwt_required()
def list_courses():
    role, user_id = _role_and_user_id()

    if role == UserRole.admin.value:
        courses = Course.query.order_by(Course.id.desc()).all()

    elif role == UserRole.teacher.value:
        courses = Course.query.filter_by(teacher_id=user_id).order_by(Course.id.desc()).all()

    elif role == UserRole.student.value:
        # student sees enrolled courses
        courses = (
            db.session.query(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .filter(Enrollment.student_id == user_id)
            .order_by(Course.id.desc())
            .all()
        )
    else:
        return {"error": "forbidden"}, 403

    return {"items": [c.to_dict() for c in courses]}, 200


@courses_bp.get("/courses/<int:course_id>")
@jwt_required()
def get_course(course_id: int):
    role, user_id = _role_and_user_id()

    course = Course.query.get_or_404(course_id)

    if role == UserRole.admin.value:
        pass
    elif role == UserRole.teacher.value:
        if course.teacher_id != user_id:
            return {"error": "forbidden"}, 403
    elif role == UserRole.student.value:
        enrolled = Enrollment.query.filter_by(course_id=course_id, student_id=user_id).first()
        if not enrolled:
            return {"error": "forbidden"}, 403
    else:
        return {"error": "forbidden"}, 403

    return course.to_dict(), 200


@courses_bp.put("/courses/<int:course_id>")
@jwt_required()
def update_course(course_id: int):
    role, user_id = _role_and_user_id()
    course = Course.query.get_or_404(course_id)

    # permissions
    if role == UserRole.admin.value:
        pass
    elif role == UserRole.teacher.value:
        if course.teacher_id != user_id:
            return {"error": "forbidden"}, 403
    else:
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    code = data.get("code")
    name = data.get("name")
    semester = data.get("semester")

    if code is not None:
        code = code.strip()
        if not code:
            return {"error": "code cannot be empty"}, 400
        existing = Course.query.filter(Course.code == code, Course.id != course_id).first()
        if existing:
            return {"error": "course code already exists"}, 409
        course.code = code

    if name is not None:
        name = name.strip()
        if not name:
            return {"error": "name cannot be empty"}, 400
        course.name = name

    if semester is not None:
        semester = semester.strip() or None
        course.semester = semester

    # optional: admin can reassign teacher
    if role == UserRole.admin.value and "teacher_id" in data:
        try:
            course.teacher_id = int(data["teacher_id"])
        except ValueError:
            return {"error": "teacher_id must be an integer"}, 400

    db.session.commit()
    return course.to_dict(), 200


@courses_bp.delete("/courses/<int:course_id>")
@jwt_required()
def delete_course(course_id: int):
    role, user_id = _role_and_user_id()
    course = Course.query.get_or_404(course_id)

    if role == UserRole.admin.value:
        pass
    elif role == UserRole.teacher.value:
        if course.teacher_id != user_id:
            return {"error": "forbidden"}, 403
    else:
        return {"error": "forbidden"}, 403

    db.session.delete(course)
    db.session.commit()
    return {"message": "deleted"}, 200
