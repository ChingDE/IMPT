"""
db/seed.py
Seeds the default admin account on first startup.

Default credentials (change immediately on first login):
  Username: admin
  Password: Admin@IMPT2026
"""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)

ADMIN_USERNAME      = "admin"
ADMIN_DEFAULT_EMAIL = "admin@impt.local"
ADMIN_DEFAULT_PASS  = "Admin@IMPT2026"


async def seed_admin(db) -> None:
    from api.auth import hash_password
    from db.repositories.repositories import UserRepository

    repo = UserRepository(db)
    if await repo.get_by_username(ADMIN_USERNAME):
        return  # Already seeded

    await repo.create(
        email=ADMIN_DEFAULT_EMAIL,
        hashed_password=hash_password(ADMIN_DEFAULT_PASS),
        first_name="IMPT",
        last_name="Administrator",
        role="admin",
        username=ADMIN_USERNAME,
        must_change_password=True,
        is_verified=True,
    )
    await db.commit()

    log.warning(
        "\n"
        "  ╔══════════════════════════════════════════════════════╗\n"
        "  ║        DEFAULT ADMIN ACCOUNT CREATED                ║\n"
        "  ║  Username : admin                                    ║\n"
        "  ║  Password : Admin@IMPT2026                           ║\n"
        "  ║  Change these on first login!                        ║\n"
        "  ╚══════════════════════════════════════════════════════╝\n"
    )
