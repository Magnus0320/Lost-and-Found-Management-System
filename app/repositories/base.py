"""Data-access layer.

Everything in this package owns a SQLAlchemy ``Session`` and is the *only*
place in the codebase allowed to touch one. Services call repositories;
routers call services. Swapping the storage engine means rewriting this
package and nothing above it.
"""
from __future__ import annotations

from sqlalchemy.orm import Session


class BaseRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def flush(self) -> None:
        self.db.flush()
