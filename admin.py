import os
from app import create_app
from app.extensions import db
from app.models import User, UserRole

ADMIN_NAME = ""
ADMIN_EMAIL = ""
ADMIN_PASSWORD = ""

app = create_app()

with app.app_context():
    existing = User.query.filter_by(email=ADMIN_EMAIL).first()
    if existing:
        print(f"Admin already exists: {existing.email} (id={existing.id})")
        raise SystemExit(0)

    admin = User(full_name=ADMIN_NAME, email=ADMIN_EMAIL.lower().strip(), role=UserRole.admin)
    admin.set_password(ADMIN_PASSWORD)

    db.session.add(admin)
    db.session.commit()

    print(f"✅ Admin created: {admin.email} (id={admin.id})")
