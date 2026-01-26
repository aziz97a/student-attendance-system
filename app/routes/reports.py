from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import func, case

from ..extensions import db
from ..models import Course, Enrollment, User, UserRole, AttendanceSession, AttendanceRecord
from ..models.attendance_record import AttendanceStatus

reports_bp = Blueprint("reports", __name__)

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

@reports_bp.get("/courses/<int:course_id>/attendance/summary")
@jwt_required()
def course_attendance_summary(course_id: int):
    claims = get_jwt() or {}
    role = claims.get("role")
    user_id = int(get_jwt_identity())

    course = Course.query.get_or_404(course_id)

    # permissions
    if role == UserRole.admin.value:
        pass
    elif role == UserRole.teacher.value and course.teacher_id == user_id:
        pass
    else:
        return {"error": "forbidden"}, 403

    now = _utc_now()

    finished_filter = ((AttendanceSession.ends_at <= now) | (AttendanceSession.is_active == False))

    # 1) total finished sessions for this course
    total_sessions = (
        db.session.query(func.count(AttendanceSession.id))
        .filter(AttendanceSession.course_id == course_id)
        .filter(finished_filter)
        .scalar()
    ) or 0

    # 2) enrolled students
    enrolled = (
        db.session.query(User.id, User.full_name, User.email)
        .join(Enrollment, Enrollment.student_id == User.id)
        .filter(Enrollment.course_id == course_id)
        .order_by(User.full_name.asc())
        .all()
    )
    student_ids = [s.id for s in enrolled]

    # If no students, return early
    if not student_ids:
        return {
            "course": {"id": course.id, "name": getattr(course, "name", None)},
            "total_sessions": total_sessions,
            "threshold_pct": 70,
            "stats": {"total_students": 0, "eligible": 0, "not_eligible": 0, "avg_attendance_pct": 0.0},
            "items": [],
        }, 200

    # If no finished sessions yet, everyone is 0%
    if total_sessions == 0:
        items = []
        for s in enrolled:
            items.append({
                "student": {"id": s.id, "full_name": s.full_name, "email": s.email},
                "attended": 0,
                "absent": 0,
                "total_sessions": 0,
                "attendance_pct": 0.0,
                "eligible": False,
            })
        return {
            "course": {"id": course.id, "name": getattr(course, "name", None)},
            "total_sessions": 0,
            "threshold_pct": 70,
            "stats": {"total_students": len(items), "eligible": 0, "not_eligible": len(items), "avg_attendance_pct": 0.0},
            "items": items,
        }, 200

    # 3) attended per student for finished sessions (present+late)
    attended_rows = (
        db.session.query(
            AttendanceRecord.student_id.label("student_id"),
            func.sum(
                case(
                    (AttendanceRecord.status.in_([AttendanceStatus.present, AttendanceStatus.late]), 1),
                    else_=0
                )
            ).label("attended")
        )
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .filter(AttendanceSession.course_id == course_id)
        .filter(finished_filter)
        .filter(AttendanceRecord.student_id.in_(student_ids))
        .group_by(AttendanceRecord.student_id)
        .all()
    )
    attended_map = {r.student_id: int(r.attended or 0) for r in attended_rows}

    # 4) build output + stats
    items = []
    eligible_count = 0
    total_pct_sum = 0.0

    for s in enrolled:
        attended = attended_map.get(s.id, 0)
        absent = total_sessions - attended  # computed
        pct = round((attended / total_sessions) * 100.0, 2)
        eligible = pct >= 70.0

        if eligible:
            eligible_count += 1
        total_pct_sum += pct

        items.append({
            "student": {"id": s.id, "full_name": s.full_name, "email": s.email},
            "attended": attended,
            "absent": absent,
            "total_sessions": total_sessions,
            "attendance_pct": pct,
            "eligible": eligible,
        })

    total_students = len(items)
    not_eligible = total_students - eligible_count
    avg_pct = round(total_pct_sum / total_students, 2) if total_students else 0.0

    return {
        "course": {"id": course.id, "name": getattr(course, "name", None)},
        "total_sessions": total_sessions,
        "threshold_pct": 70,
        "stats": {
            "total_students": total_students,
            "eligible": eligible_count,
            "not_eligible": not_eligible,
            "avg_attendance_pct": avg_pct,
        },
        "items": items,
    }, 200
