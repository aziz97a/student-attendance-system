from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from sqlalchemy import func, case

from ..extensions import db
from ..models import Course, Enrollment, User, UserRole, AttendanceSession, AttendanceRecord
from ..models.attendance_record import AttendanceStatus

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
    planned_sessions = data.get("planned_sessions", 14)

    try:
        planned_sessions = int(planned_sessions)
    except (TypeError, ValueError):
        return {"error": "planned_sessions must be an integer"}, 400

    if planned_sessions < 1 or planned_sessions > 200:
        return {"error": "planned_sessions must be between 1 and 200"}, 400

    if not code or not name:
        return {"error": "code and name are required"}, 400

    # who owns the course?
    if role == UserRole.teacher.value:
        teacher_id = user_id
    else:
        teacher_id = data.get("teacher_id")
        if not teacher_id:
            return {"error": "teacher_id is required for admin"}, 400
        try:
            teacher_id = int(teacher_id)
        except (TypeError, ValueError):
            return {"error": "teacher_id must be an integer"}, 400

        teacher = User.query.get(teacher_id)
        if not teacher or teacher.role != UserRole.teacher:
            return {"error": "teacher_id must belong to a teacher"}, 400

    if Course.query.filter_by(code=code).first():
        return {"error": "course code already exists"}, 409

    course = Course(
        code=code,
        name=name,
        semester=semester,
        teacher_id=teacher_id,
        planned_sessions=planned_sessions,
    )
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




def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

@courses_bp.get("/courses/<int:course_id>/eligibility")
@jwt_required()
def course_eligibility(course_id: int):
    claims = get_jwt() or {}
    role = claims.get("role")
    user_id = int(get_jwt_identity())

    course = Course.query.get_or_404(course_id)

    # permissions: admin OR the teacher who owns the course
    if role == UserRole.admin.value:
        pass
    elif role == UserRole.teacher.value and course.teacher_id == user_id:
        pass
    else:
        return {"error": "forbidden"}, 403

    now = _utc_now()

    # 1) finished sessions count (ended or manually closed)
    finished_sessions = (
        db.session.query(func.count(AttendanceSession.id))
        .filter(AttendanceSession.course_id == course_id)
        .filter((AttendanceSession.ends_at <= now) | (AttendanceSession.is_active == False))
        .scalar()
    ) or 0

    # 2) planned sessions (fixed denominator for eligibility)
    planned_sessions = int(getattr(course, "planned_sessions", 0) or 0)

    # Safety: planned should never be less than finished
    denom = max(planned_sessions, finished_sessions)

    # 3) list enrolled students
    enrolled = (
        db.session.query(User.id, User.full_name, User.email)
        .join(Enrollment, Enrollment.student_id == User.id)
        .filter(Enrollment.course_id == course_id)
        .order_by(User.full_name.asc())
        .all()
    )
    student_ids = [row.id for row in enrolled]

    # If denom is 0 (shouldn't happen, but safe)
    if denom == 0:
        items = []
        for s in enrolled:
            items.append({
                "student": {"id": s.id, "full_name": s.full_name, "email": s.email},
                "attended": 0,
                "finished_sessions": 0,
                "planned_sessions": 0,
                "attendance_pct": 0.0,
                "eligible": False,
            })
        return {
            "course_id": course_id,
            "finished_sessions": 0,
            "planned_sessions": 0,
            "threshold_pct": 70,
            "items": items,
        }, 200

    # 4) attended counts per student for FINISHED sessions only
    attended_counts = (
        db.session.query(
            AttendanceRecord.student_id.label("student_id"),
            func.sum(
                case(
                    (AttendanceRecord.status.in_([AttendanceStatus.present, AttendanceStatus.late]), 1),
                    else_=0,
                )
            ).label("attended"),
        )
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .filter(AttendanceSession.course_id == course_id)
        .filter((AttendanceSession.ends_at <= now) | (AttendanceSession.is_active == False))
        .filter(AttendanceRecord.student_id.in_(student_ids))
        .group_by(AttendanceRecord.student_id)
        .all()
    )

    attended_map = {row.student_id: int(row.attended or 0) for row in attended_counts}

    # 5) build response
    items = []
    eligible_count = 0

    for s in enrolled:
        attended = attended_map.get(s.id, 0)

        # Eligibility is based on PLANNED (fixed) denominator
        attendance_pct = round((attended / denom) * 100.0, 2)
        eligible = attendance_pct >= 70.0
        if eligible:
            eligible_count += 1

        items.append({
            "student": {"id": s.id, "full_name": s.full_name, "email": s.email},
            "attended": attended,
            "absent_so_far": max(0, finished_sessions - attended),   # computed
            "finished_sessions": finished_sessions,
            "planned_sessions": denom,
            "attendance_pct": attendance_pct,
            "eligible": eligible,
        })

    return {
        "course_id": course_id,
        "finished_sessions": finished_sessions,          # progress numerator
        "planned_sessions": denom,                       # progress denominator + eligibility denominator
        "progress": f"{finished_sessions}/{denom}",
        "threshold_pct": 70,
        "eligible_count": eligible_count,
        "total_students": len(items),
        "items": items,
    }, 200



# planned_sessions update
@courses_bp.patch("/courses/<int:course_id>/planned-sessions")
@jwt_required()
def update_planned_sessions(course_id: int):
    role, user_id = _role_and_user_id()

    course = Course.query.get_or_404(course_id)

    # permission check
    if role == UserRole.admin.value:
        pass
    elif role == UserRole.teacher.value and course.teacher_id == user_id:
        pass
    else:
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    planned_sessions = data.get("planned_sessions")

    if planned_sessions is None:
        return {"error": "planned_sessions is required"}, 400

    try:
        planned_sessions = int(planned_sessions)
    except (TypeError, ValueError):
        return {"error": "planned_sessions must be an integer"}, 400

    if planned_sessions < 1 or planned_sessions > 200:
        return {"error": "planned_sessions must be between 1 and 200"}, 400
     
    now = _utc_now()
    # count finished sessions
    finished_sessions = (
        db.session.query(func.count(AttendanceSession.id))
        .filter(AttendanceSession.course_id == course.id)
        .filter(
            (AttendanceSession.ends_at <= now) |
            (AttendanceSession.is_active == False)
        )
        .scalar()
    ) or 0

    if planned_sessions < finished_sessions:
        return {
            "error": "planned_sessions cannot be less than finished sessions",
            "finished_sessions": finished_sessions,
        }, 400

    course.planned_sessions = planned_sessions
    db.session.commit()

    return {
        "message": "planned_sessions updated",
        "course_id": course.id,
        "planned_sessions": course.planned_sessions,
        "finished_sessions": finished_sessions,
    }, 200
