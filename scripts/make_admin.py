#!/usr/bin/env python
"""Grant or revoke administrator access from the command line.

The first admin has to be made out-of-band -- the /admin/users/{id}/role route
needs an admin to call it, so there would otherwise be no way in. After that,
admins can promote each other through the UI.

    python scripts/make_admin.py you@example.com
    python scripts/make_admin.py you@example.com --revoke
    python scripts/make_admin.py --list

Inside Docker:

    docker compose exec api python scripts/make_admin.py you@example.com
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal  # noqa: E402
from app.repositories.user_repo import UserRepository  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", nargs="?", help="Address of the account to change.")
    parser.add_argument("--revoke", action="store_true", help="Remove admin access.")
    parser.add_argument("--list", action="store_true", help="Show current admins.")
    args = parser.parse_args()

    with SessionLocal() as db:
        users = UserRepository(db)

        if args.list:
            admins = users.list_admins()
            if not admins:
                print("No administrators yet.")
            for u in admins:
                print(f"  {u.email}  ({u.first_name} {u.last_name})")
            print(f"\n{len(admins)} admin(s) of {users.count()} account(s).")
            return 0

        if not args.email:
            parser.error("give an email address, or --list")

        user = users.get_by_email(args.email)
        if user is None:
            print(f"No account with email {args.email!r}.", file=sys.stderr)
            print("Register it in the app first, then run this again.", file=sys.stderr)
            return 1

        if not user.is_verified and not args.revoke:
            print(f"Warning: {user.email} has not verified its email yet.",
                  file=sys.stderr)

        users.set_admin(user, not args.revoke)
        db.commit()

        state = "revoked from" if args.revoke else "granted to"
        print(f"Administrator access {state} {user.email} "
              f"({user.first_name} {user.last_name}).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
