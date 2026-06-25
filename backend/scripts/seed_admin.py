"""สร้าง admin user เริ่มต้น.

Usage: python -m scripts.seed_admin <username> <email> <password>
ค่า default: admin / admin@example.com / admin123
"""
import sys

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.user import User


def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    email = sys.argv[2] if len(sys.argv) > 2 else "admin@example.com"
    password = sys.argv[3] if len(sys.argv) > 3 else "admin123"

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == username).first():
            print(f"user '{username}' มีอยู่แล้ว")
            return
        db.add(
            User(
                username=username,
                email=email,
                display_name="Administrator",
                role="admin",
                password_hash=hash_password(password),
            )
        )
        db.commit()
        print(f"สร้าง admin '{username}' เรียบร้อย (password: {password})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
