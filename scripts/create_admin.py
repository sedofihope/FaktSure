import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import User


def main() -> None:
    """Create an administrator interactively without a default password."""

    if get_settings().app_env.lower() == "development":
        Base.metadata.create_all(bind=engine)
    full_name = input("Administrator name: ").strip()
    email = input("Administrator email: ").strip().lower()
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if not full_name or not email:
        raise SystemExit("Name and email are required")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    if password != confirmation:
        raise SystemExit("Passwords do not match")

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)):
            raise SystemExit("A user with this email already exists")
        db.add(User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role="ADMIN",
        ))
        db.commit()
    print(f"Administrator account created for {email}")


if __name__ == "__main__":
    main()