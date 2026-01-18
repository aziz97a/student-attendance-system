from __future__ import annotations

import secrets
from datetime import datetime, date, timedelta, timezone

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

from app.models.user import User

from ..extensions import db
from ..models import AttendanceSession, AttendanceRecord, Enrollment, Course, UserRole
from ..models.attendance_record import AttendanceStatus

sessions_bp = Blueprint("sessions", __name__)

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _ensure_tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

  # -----------------------------
# CREATE SESSION (teacher uses current GPS)
# -----------------------------
@sessions_bp.post("/sessions")
@jwt_required()
def create_session():
    claims = get_jwt() or {}
    role = claims.get("role")
    user_id = int(get_jwt_identity())

    if role not in (UserRole.admin.value, UserRole.teacher.value):
        return {"error": "forbidden"}, 403

    data = request.get_json(silent=True) or {}
    course_id = data.get("course_id")
    lat = data.get("lat")
    lng = data.get("lng")
    radius_m = data.get("radius_m", 50)
    duration_min = data.get("duration_min", 15)  # attendance window

    if course_id is None or lat is None or lng is None:
        return {"error": "course_id, lat, lng are required"}, 400

    try:
        course_id = int(course_id)
        lat = float(lat)
        lng = float(lng)
        radius_m = int(radius_m)
        duration_min = int(duration_min)
    except (TypeError, ValueError):
        return {"error": "invalid types for course_id/lat/lng/radius_m/duration_min"}, 400

    if radius_m < 10 or radius_m > 500:
        return {"error": "radius_m must be between 10 and 500"}, 400

    if duration_min < 1 or duration_min > 240:
        return {"error": "duration_min must be between 1 and 240"}, 400

    course = Course.query.get_or_404(course_id)

    # teacher can only start session for their course
    if role == UserRole.teacher.value and course.teacher_id != user_id:
        return {"error": "forbidden"}, 403

    # close any existing active session for this course
    now = _utc_now()
    AttendanceSession.query.filter_by(course_id=course_id, is_active=True).update({
        "is_active": False,
        "ends_at": now,
    })

    token = secrets.token_urlsafe(24)
    starts_at = now
    ends_at = now + timedelta(minutes=duration_min)

    session = AttendanceSession(
        course_id=course_id,
        teacher_id=course.teacher_id,
        session_date=date.today(),
        starts_at=starts_at,
        ends_at=ends_at,
        lat=lat,
        lng=lng,
        radius_m=radius_m,
        is_active=True,
        qr_token=token,
    )

    db.session.add(session)
    db.session.commit()
    return session.to_dict(), 201


# -----------------------------
# CLOSE SESSION + MARK ABSENT
# -----------------------------
@sessions_bp.patch("/sessions/<int:session_id>/close")
@jwt_required()
def close_session(session_id: int):
    claims = get_jwt() or {}
    role = claims.get("role")
    user_id = int(get_jwt_identity())

    session = AttendanceSession.query.get_or_404(session_id)
    course = Course.query.get_or_404(session.course_id)

    if role == UserRole.admin.value:
        pass
    elif role == UserRole.teacher.value and course.teacher_id == user_id:
        pass
    else:
        return {"error": "forbidden"}, 403

    if not session.is_active:
        return {"message": "already closed", "session": session.to_dict()}, 200

    now = _utc_now()
    session.is_active = False
    session.ends_at = now

    # all enrolled students
    enrolled_ids = {e.student_id for e in Enrollment.query.filter_by(course_id=session.course_id).all()}

    # who already has a record (present/late/absent)
    existing_ids = {r.student_id for r in AttendanceRecord.query.filter_by(session_id=session.id).all()}

    # absentees = enrolled - recorded
    absent_ids = enrolled_ids - existing_ids

    for sid in absent_ids:
        db.session.add(
            AttendanceRecord(
                session_id=session.id,
                student_id=sid,
                status=AttendanceStatus.absent,
                checked_in_at=None,
                note="auto-marked absent (no check-in)",
            )
        )

    db.session.commit()
    return {"message": "session closed", "session": session.to_dict()}, 200


# -----------------------------
# LIST SESSIONS (teacher/admin)
# -----------------------------
@sessions_bp.get("/sessions")
@jwt_required()
def list_sessions():
    claims = get_jwt() or {}
    role = claims.get("role")
    user_id = int(get_jwt_identity())

    course_id = request.args.get("course_id", None, type=int)

    q = AttendanceSession.query
    if course_id:
        q = q.filter_by(course_id=course_id)

    if role == UserRole.admin.value:
        sessions = q.order_by(AttendanceSession.id.desc()).all()
    elif role == UserRole.teacher.value:
        sessions = q.join(Course, AttendanceSession.course_id == Course.id)\
                   .filter(Course.teacher_id == user_id)\
                   .order_by(AttendanceSession.id.desc()).all()
    else:
        return {"error": "forbidden"}, 403

    return {"items": [s.to_dict() for s in sessions]}, 200


@sessions_bp.get("/sessions/<int:session_id>/attendance")
@jwt_required()
def session_attendance(session_id: int):
    claims = get_jwt() or {}
    role = claims.get("role")
    user_id = int(get_jwt_identity())

    session = AttendanceSession.query.get_or_404(session_id)
    course = Course.query.get_or_404(session.course_id)

    # permissions
    if role == UserRole.admin.value:
        pass
    elif role == UserRole.teacher.value and course.teacher_id == user_id:
        pass
    else:
        return {"error": "forbidden"}, 403

    # all enrolled students in this course
    enrollments = (
        Enrollment.query
        .filter_by(course_id=course.id)
        .all()
    )
    student_ids = [e.student_id for e in enrollments]

    # fetch all users in one query
    students = (
        User.query
        .filter(User.id.in_(student_ids))
        .all()
    )
    students_by_id = {u.id: u for u in students}

    # fetch existing attendance records for this session
    records = (
        AttendanceRecord.query
        .filter_by(session_id=session.id)
        .all()
    )
    record_by_student = {r.student_id: r for r in records}

    # build response: everyone enrolled gets a row
    items = []
    present_count = late_count = absent_count = 0

    for sid in student_ids:
        student = students_by_id.get(sid)

        rec = record_by_student.get(sid)
        if rec:
            status = rec.status.value
            checked_in_at = rec.checked_in_at.isoformat() if rec.checked_in_at else None
            distance_m = rec.distance_m
        else:
            status = AttendanceStatus.absent.value
            checked_in_at = None
            distance_m = None

        if status == AttendanceStatus.present.value:
            present_count += 1
        elif status == AttendanceStatus.late.value:
            late_count += 1
        else:
            absent_count += 1

        items.append({
            "student": {
                "id": student.id if student else sid,
                "full_name": student.full_name if student else None,
                "email": student.email if student else None,
            },
            "status": status,
            "checked_in_at": checked_in_at,
            "distance_m": distance_m,
        })

    return {
        "session": {
            "id": session.id,
            "course_id": session.course_id,
            "starts_at": session.starts_at.isoformat(),
            "ends_at": session.ends_at.isoformat(),
            "is_active": session.is_active,
        },
        "counts": {
            "present": present_count,
            "late": late_count,
            "absent": absent_count,
            "total": len(student_ids),
        },
        "items": items,
    }, 200
