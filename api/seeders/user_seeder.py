"""
User seeder to create the initial admin user.
"""
from core.config import settings
from core.database import get_db, init_db
from enums.user_role import UserRole
from models.user import User
from services.auth_service import get_password_hash, get_user_by_email


def seed_admin_user() -> None:
    """Create the admin user if it doesn't already exist."""
    init_db()
    db = next(get_db())
    try:
        existing_admin = get_user_by_email(db, settings.admin_email)
        if existing_admin:
            print(f"[OK] Admin user already exists: {settings.admin_email}")
            return

        admin_user = User(
            name="Léo Guillaume",
            email=settings.admin_email,
            hashed_password=get_password_hash(settings.admin_password),
            role=UserRole.ADMIN.value,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()
        print(f"[OK] Admin user created: {settings.admin_email}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Failed to seed admin user: {exc}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin_user()
