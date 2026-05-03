"""
db/seed.py
Seeds the default admin account on first startup.

Credentials (hardcoded for first login — admin MUST change on first use):
    Username: admin
    Password: Admin@IMPT2026

The must_change_password flag is set to True so the frontend forces
a password change immediately after first login.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

ADMIN_USERNAME       = "admin"
ADMIN_DEFAULT_EMAIL  = "admin@impt.local"   # placeholder — admin should update this
ADMIN_DEFAULT_PASS   = "Admin@IMPT2026"


async def seed_admin(db) -> None:
    """
    Called once at startup (lifespan). Creates the default admin account
    only if no user with username='admin' exists.
    Safe to call on every restart — does nothing if the account is present.
    """
    from api.auth import hash_password
    from db.repositories import UserRepository

    repo = UserRepository(db)

    # Check by username (not email — admin may change email later)
    existing = await repo.get_by_username(ADMIN_USERNAME)
    if existing:
        return  # already seeded, do nothing

    await repo.create(
        email=ADMIN_DEFAULT_EMAIL,
        hashed_password=hash_password(ADMIN_DEFAULT_PASS),
        full_name="IMPT Administrator",
        role="admin",
        username=ADMIN_USERNAME,
        must_change_password=True,
    )
    await db.commit()

    log.warning(
        "\n"
        "  ╔══════════════════════════════════════════════════════╗\n"
        "  ║        DEFAULT ADMIN ACCOUNT CREATED                ║\n"
        "  ║                                                      ║\n"
        "  ║  Username : admin                                    ║\n"
        "  ║  Password : Admin@IMPT2026                           ║\n"
        "  ║                                                      ║\n"
        "  ║  You will be asked to change these on first login.   ║\n"
        "  ╚══════════════════════════════════════════════════════╝\n"
    )
