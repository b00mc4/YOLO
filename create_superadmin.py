from __future__ import annotations
import argparse
import asyncio
from sqlalchemy import select
from app.core.security import hash_password
from app.db.session import async_session_maker
from app.db.base import Base
from app.models.user import User, UserRole


async def create_superadmin(username: str, email: str, fullname: str, password: str) -> None:
    async with async_session_maker() as db:
        result = await db.execute(
            select(User).where((User.username == username) | (User.email == email))
        )
        existing_user = result.scalar_one_or_none()

        if existing_user is not None:
            print(f"User already exists: username={existing_user.username}, email={existing_user.email}")
            return

        user = User(
            username=username,
            fullname=fullname,
            email=email,
            role=UserRole.SUPERADMIN,
            village_id=None,
            hashpassword=hash_password(password),
            is_active=True,
            is_verify=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        print("Superadmin created successfully")
        print(f"id: {user.id}")
        print(f"username: {user.username}")
        print(f"email: {user.email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the first superadmin user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--fullname", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    asyncio.run(
        create_superadmin(
            username=args.username,
            email=args.email,
            fullname=args.fullname,
            password=args.password,
        )
    )


if __name__ == "__main__":
    main()