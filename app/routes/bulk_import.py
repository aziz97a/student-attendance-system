import csv
import io

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import User, UserRole, Student, Course, Enrollment

bulk_bp = Blueprint("bulk", __name__)

def _role_and_user_id():
    claims = get_jwt()
    return claims.get("role"), int(get_jwt_identity())


@bulk_bp.post("/enrollments/import")
@jwt_required()
def import_students_csv():
    """
    multipart/form-data:
      - course_id: int
      - file: CSV file (columns: email, student_no, full_name, department, year_level)
    """
    role, user_id = _role_and_user_id()

    if role not in (UserRole.admin.value, UserRole.teacher.value):
        return {"error": "forbidden"}, 403

    course_id = request.form.get("course_id")
    if not course_id:
        return {"error": "course_id is required (form field)"}, 400

    try:
        course_id = int(course_id)
    except ValueError:
        return {"error": "course_id must be an integer"}, 400

    course = Course.query.get(course_id)
    if not course:
        return {"error": "course not found"}, 404

    # teacher can import only for their own course
    if role == UserRole.teacher.value and course.teacher_id != user_id:
        return {"error": "forbidden"}, 403

    if "file" not in request.files:
        return {"error": "file is required"}, 400

    file = request.files["file"]
    if not file or file.filename.strip() == "":
        return {"error": "file is required"}, 400

    # Read CSV safely
    try:
        stream = io.TextIOWrapper(file.stream, encoding="utf-8", newline="")
        reader = csv.DictReader(stream)
    except Exception:
        return {"error": "invalid CSV file"}, 400

    required_cols = {"email", "student_no", "full_name"}
    if not reader.fieldnames or not required_cols.issubset(set([c.strip() for c in reader.fieldnames])):
        return {
            "error": "CSV must include columns: email, student_no, full_name (optional: department, year_level)"
        }, 400

    summary = {
        "created_users": 0,
        "updated_profiles": 0,
        "enrolled": 0,
        "already_enrolled": 0,
        "skipped_invalid": 0,
        "errors": [],
    }

    # Process rows
    for idx, row in enumerate(reader, start=2):  # header line is 1
        email = (row.get("email") or "").strip().lower()
        student_no = (row.get("student_no") or "").strip()
        full_name = (row.get("full_name") or "").strip()
        department = (row.get("department") or "").strip() or None
        year_level_raw = (row.get("year_level") or "").strip()

        if not email or not student_no or not full_name:
            summary["skipped_invalid"] += 1
            summary["errors"].append(f"Line {idx}: missing email/student_no/full_name")
            continue

        # year_level optional
        year_level = None
        if year_level_raw:
            try:
                year_level = int(year_level_raw)
            except ValueError:
                summary["skipped_invalid"] += 1
                summary["errors"].append(f"Line {idx}: year_level must be integer")
                continue

        # 1) Find or create user
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(full_name=full_name, email=email, role=UserRole.student)
            user.set_password(student_no)                # ✅ initial password = student_no
            user.must_change_password = True            # ✅ force change on first login
            db.session.add(user)
            db.session.flush()  # get user.id
            summary["created_users"] += 1
        else:
            # If user exists but is not student, skip for safety
            if user.role != UserRole.student:
                summary["skipped_invalid"] += 1
                summary["errors"].append(f"Line {idx}: email belongs to non-student user")
                continue

        # 2) Ensure student profile exists and update it
        profile = Student.query.get(user.id)
        if not profile:
            profile = Student(user_id=user.id)
            db.session.add(profile)

        # Unique check for student_no (if your schema enforces it, this helps nicer errors)
        existing_no = Student.query.filter(Student.student_no == student_no, Student.user_id != user.id).first()
        if existing_no:
            summary["skipped_invalid"] += 1
            summary["errors"].append(f"Line {idx}: student_no already used by another student")
            continue

        profile.student_no = student_no
        profile.department = department
        profile.year_level = year_level
        summary["updated_profiles"] += 1

        # 3) Enroll student
        enrollment = Enrollment(course_id=course_id, student_id=user.id)
        try:
            db.session.add(enrollment)
            db.session.flush()
            summary["enrolled"] += 1
        except IntegrityError:
            db.session.rollback()
            # rollback cancels pending changes; re-attach objects by restarting transaction chunk
            # easiest: start a new transaction per row
            db.session.begin()
            summary["already_enrolled"] += 1
            continue

    db.session.commit()
    return {"course_id": course_id, "summary": summary}, 200
