from datetime import datetime, timezone

from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy import func

from ..extensions import db
from ..models import (
    UserRole,
    Enrollment,
    Course,
    AttendanceSession,
    AttendanceRecord,
)
from ..models.attendance_record import AttendanceStatus

students_bp = Blueprint("students", __name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@students_bp.get("/students/me/attendance")
@jwt_required()
def my_attendance_history():
    # ---- auth / role ----
    claims = get_jwt() or {}
    role = claims.get("role")
    if role != UserRole.student.value:
        return {"error": "forbidden"}, 403

    student_id = int(get_jwt_identity())
    now = _utc_now()

    # ---- enrolled courses (with planned_sessions included) ----
    enrollments = (
        db.session.query(
            Enrollment.course_id,
            Course.name,
            Course.planned_sessions,
        )
        .join(Course, Course.id == Enrollment.course_id)
        .filter(Enrollment.student_id == student_id)
        .order_by(Course.name.asc())
        .all()
    )

    courses_output = []
    overall_planned = 0
    overall_attended = 0
    overall_finished = 0  # useful progress metric

    for course_id, course_name, planned_sessions in enrollments:
        planned_sessions = int(planned_sessions or 0)

        # 1) finished sessions in this course (ended OR manually closed)
        finished_sessions_rows = (
            db.session.query(AttendanceSession.id, AttendanceSession.session_date)
            .filter(AttendanceSession.course_id == course_id)
            .filter((AttendanceSession.ends_at <= now) | (AttendanceSession.is_active == False))
            .order_by(AttendanceSession.session_date.asc())
            .all()
        )

        finished_session_ids = [row.id for row in finished_sessions_rows]
        finished_sessions = len(finished_session_ids)

        # 2) attendance records for THIS student for these finished sessions
        #    (missing record => absent)
        record_rows = []
        if finished_session_ids:
            record_rows = (
                db.session.query(
                    AttendanceRecord.session_id,
                    AttendanceRecord.status,
                    AttendanceRecord.checked_in_at,
                    AttendanceRecord.distance_m,
                )
                .filter(AttendanceRecord.student_id == student_id)
                .filter(AttendanceRecord.session_id.in_(finished_session_ids))
                .all()
            )

        record_map = {r.session_id: r for r in record_rows}

        # 3) build per-session history (include absents)
        records_out = []
        attended = 0

        for s in finished_sessions_rows:
            rec = record_map.get(s.id)

            if rec:
                status = rec.status
                checked_in_at = rec.checked_in_at.isoformat() if rec.checked_in_at else None
                distance_m = rec.distance_m
            else:
                status = AttendanceStatus.absent
                checked_in_at = None
                distance_m = None

            # attended = present OR late
            if status in (AttendanceStatus.present, AttendanceStatus.late):
                attended += 1

            records_out.append(
                {
                    "session_id": s.id,
                    "session_date": s.session_date.isoformat() if s.session_date else None,
                    "status": status.value,
                    "checked_in_at": checked_in_at,
                    "distance_m": distance_m,
                }
            )

        absent_so_far = max(0, finished_sessions - attended)

        # 4) eligibility % uses PLANNED denominator (fixed course plan)
        denom = max(planned_sessions, finished_sessions)  # safety: planned should never be < finished
        pct = round((attended / denom) * 100.0, 2) if denom else 0.0
        eligible = pct >= 70.0

        overall_planned += denom
        overall_attended += attended
        overall_finished += finished_sessions

        courses_output.append(
            {
                "course_id": course_id,
                "course_name": course_name,
                "planned_sessions": denom,
                "finished_sessions": finished_sessions,
                "progress": f"{finished_sessions}/{denom}",
                "attended": attended,
                "absent_so_far": absent_so_far,
                "attendance_pct": pct,
                "eligible": eligible,
                "records": records_out,  # finished sessions only, includes absent
            }
        )

    overall_pct = round((overall_attended / overall_planned) * 100.0, 2) if overall_planned else 0.0

    return {
        "student_id": student_id,
        "overall": {
            "planned_sessions": overall_planned,
            "finished_sessions": overall_finished,
            "progress": f"{overall_finished}/{overall_planned}" if overall_planned else "0/0",
            "attended": overall_attended,
            "attendance_pct": overall_pct,
            "eligible": overall_pct >= 70.0,
        },
        "courses": courses_output,
    }, 200
