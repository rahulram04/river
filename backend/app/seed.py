"""Initialize an admin without publishing any default passwords."""
import argparse
import getpass
from sqlalchemy import select
from app.db import SessionLocal
from app.db_models import User
from app.domain import get_issuance
from app.services import grant_user
from app.auth import ph
from app.config import get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("New admin password (12+ characters): ")
    if len(password) < 12:
        raise SystemExit("Password must have at least 12 characters")
    with SessionLocal() as db:
        email = args.admin_email.strip().lower()
        if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
            raise SystemExit("Account already exists. This command will not elevate it.")
        get_issuance(db)
        user = User(email=email, password_hash=ph.hash(password), role="ADMIN")
        db.add(user)
        db.flush()
        grant_user(db, user, get_settings().initial_play_credits)
        db.commit()
    print("Admin account created. Password was not saved in CLI history.")


if __name__ == "__main__":
    main()
