from __future__ import annotations

import math
from datetime import datetime, timezone

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import AttendanceSession, AttendanceRecord, Enrollment, UserRole
from ..models.attendance_record import AttendanceStatus

attendance_bp = Blueprint("attendance", __name__)

PRESENT_WINDOW_MIN = 5
LATE_WINDOW_MIN = 15

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _ensure_tz(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def haversine_m(lat1, lon1, lat2, lon2) -> int:
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(round(R * c))

def compute_status(session: AttendanceSession, now: datetime) -> AttendanceStatus | None:
    starts_at = _ensure_tz(session.starts_at)
    elapsed_min = (now - starts_at).total_seconds() / 60.0

    if elapsed_min <= PRESENT_WINDOW_MIN:
        return AttendanceStatus.present
    if elapsed_min <= LATE_WINDOW_MIN:
        return AttendanceStatus.late
    return None  # window closed


@attendance_bp.post("/attendance/checkin")
@jwt_required()
def checkin():
    claims = get_jwt() or {}
    role = claims.get("role")
    student_id = int(get_jwt_identity())

    if role != UserRole.student.value:
        return {"error": "forbidden (student only)"}, 403

    data = request.get_json(silent=True) or {}
    qr_token = (data.get("qr_token") or "").strip()
    lat = data.get("lat")
    lng = data.get("lng")

    if not qr_token or lat is None or lng is None:
        return {"error": "qr_token, lat, lng are required"}, 400

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return {"error": "lat/lng must be numbers"}, 400

    session = AttendanceSession.query.filter_by(qr_token=qr_token).first()
    if not session:
        return {"error": "invalid qr_token"}, 404

    if not session.is_active:
        return {"error": "session is closed"}, 400

    now = _utc_now()

    # time window check (auto-expire)
    ends_at = _ensure_tz(session.ends_at)
    if now > ends_at:
        session.is_active = False
        db.session.commit()
        return {"error": "session expired"}, 400
 
    # enrollment check
    if not Enrollment.query.filter_by(course_id=session.course_id, student_id=student_id).first():
        return {"error": "not enrolled in this course"}, 403

    # compute status
    status = compute_status(session, now)
    if status is None:
        return {"error": "check-in window closed"}, 400

    # location check
    distance = haversine_m(session.lat, session.lng, lat, lng)
    if distance > session.radius_m:
        return {
            "error": "too far from class",
            "distance_m": distance,
            "allowed_radius_m": session.radius_m,
        }, 403

    record = AttendanceRecord(
        session_id=session.id,
        student_id=student_id,
        status=status,
        checked_in_at=now,
        student_lat=lat,
        student_lng=lng,
        distance_m=distance,
        note=None,
    )

    try:
        db.session.add(record)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return {"error": "already checked in"}, 409

    return {"message": "checked in", "record": record.to_dict()}, 201
