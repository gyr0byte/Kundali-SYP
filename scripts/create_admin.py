"""Administrative CLI script to create or promote an admin user safely.

Usage:
    python scripts/create_admin.py --email admin@example.com

Security:
    Password is read from the ADMIN_PASSWORD environment variable or prompted via getpass.
    Passwords are NEVER accepted as command-line arguments and NEVER printed to logs/stdout.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

# Add backend directory to sys.path so app modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.clock import SystemClock
from app.core.permissions import UserRole
from app.core.security import hash_password, validate_password
from app.db.models import User
from app.db.session import get_session_factory
from app.services.auth_service import normalize_email


def create_admin_user(
    db: Session,
    email: str,
    password: str,
    for_testing: bool = False,
) -> User:
    """Create a new admin user or promote an existing user to admin."""
    clean_email = normalize_email(email)

    valid_pass, err = validate_password(password, clean_email)
    if not valid_pass:
        raise ValueError(err or "Invalid password")

    user = db.scalar(select(User).where(User.email == clean_email))
    hashed = hash_password(password, for_testing=for_testing)
    now = SystemClock().now()

    if user:
        user.role = UserRole.ADMIN
        user.password_hash = hashed
        user.is_active = True
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_at = now
    else:
        user = User(
            email=clean_email,
            password_hash=hashed,
            role=UserRole.ADMIN,
            language="en",
            is_active=True,
            failed_login_attempts=0,
            created_at=now,
            updated_at=now,
        )
        db.add(user)

    db.commit()
    db.refresh(user)
    return user


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Create or promote an administrator account.")
    parser.add_argument("--email", required=True, help="Administrator email address")
    args = parser.parse_args()

    # Read password from environment or secure prompt (NEVER from CLI args)
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass("Enter administrator password: ")

    if not password:
        print("Error: Password cannot be empty.", file=sys.stderr)
        sys.exit(1)

    factory = get_session_factory()
    with factory() as session:
        try:
            admin = create_admin_user(session, email=args.email, password=password)
            print(f"Successfully configured admin user: {admin.email}")
        except Exception as e:
            print(f"Error creating admin: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
