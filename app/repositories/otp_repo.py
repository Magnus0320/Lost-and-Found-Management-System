from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import OtpPurpose, OtpToken
from app.repositories.base import BaseRepository


class OtpRepository(BaseRepository):
    def create(
        self, user_id: int, code_hash: str, purpose: OtpPurpose, expires_at: datetime
    ) -> OtpToken:
        token = OtpToken(
            user_id=user_id,
            code_hash=code_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        self.db.add(token)
        self.db.flush()
        return token

    def active_for_user(self, user_id: int, purpose: OtpPurpose) -> list[OtpToken]:
        stmt = (
            select(OtpToken)
            .where(
                OtpToken.user_id == user_id,
                OtpToken.purpose == purpose,
                OtpToken.consumed_at.is_(None),
                OtpToken.expires_at > datetime.now(tz=timezone.utc),
            )
            .order_by(OtpToken.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def consume(self, token: OtpToken) -> OtpToken:
        token.consumed_at = datetime.now(tz=timezone.utc)
        self.db.add(token)
        self.db.flush()
        return token
