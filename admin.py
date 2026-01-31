import os
from app import create_app
from app.extensions import db
from app.models import User, UserRole

ADMIN_NAME = os.getenv("ADMIN_NAME", "Administrator")
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL", "") or "").lower().strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

if not ADMIN_EMAIL or not ADMIN_PASSWORD:
    raise SystemExit("ADMIN_EMAIL and ADMIN_PASSWORD must be set")

app = create_app()

with app.app_context():
    existing = User.query.filter_by(email=ADMIN_EMAIL).first()
    if existing:
        print(f"Admin already exists: {existing.email} (id={existing.id})")
        raise SystemExit(0)

    admin = User(full_name=ADMIN_NAME, email=ADMIN_EMAIL, role=UserRole.admin)
    admin.set_password(ADMIN_PASSWORD)

    db.session.add(admin)
    db.session.commit()

    print(f"✅ Admin created: {admin.email} (id={admin.id})")
