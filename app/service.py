from __future__ import annotations

import hashlib
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Optional, cast

from app.db import Database


class LinkNotFoundError(Exception):
    pass


class LinkExpiredError(Exception):
    pass


class AliasInUseError(Exception):
    pass


class LinkService:
    def __init__(self, db: Database, short_code_length: int = 7) -> None:
        self.db = db
        self.short_code_length = short_code_length
        self._alphabet = string.ascii_letters + string.digits

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _new_code(self) -> str:
        return "".join(secrets.choice(self._alphabet) for _ in range(self.short_code_length))

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_ip(ip: Optional[str]) -> Optional[str]:
        if not ip:
            return None
        return hashlib.sha256(ip.encode("utf-8")).hexdigest()

    def create_link(
        self,
        original_url: str,
        custom_alias: Optional[str],
        created_by: Optional[str],
        expires_in_minutes: Optional[int],
    ) -> dict:
        now = self._now()
        expires_at = now + timedelta(minutes=expires_in_minutes) if expires_in_minutes else None
        url_hash = self._hash(original_url)

        with self.db.connection() as conn:
            existing = conn.execute(
                """
                SELECT short_code, original_url, created_at, expires_at
                FROM links
                WHERE original_url_hash = ?
                AND IFNULL(created_by, '') = IFNULL(?, '')
                ORDER BY id DESC
                LIMIT 1
                """,
                (url_hash, created_by),
            ).fetchone()
            if existing:
                return {
                    "short_code": existing["short_code"],
                    "original_url": existing["original_url"],
                    "created_at": datetime.fromisoformat(existing["created_at"]),
                    "expires_at": datetime.fromisoformat(existing["expires_at"]) if existing["expires_at"] else None,
                    "already_exists": True,
                }

            if custom_alias:
                alias_used = conn.execute(
                    "SELECT 1 FROM links WHERE short_code = ?",
                    (custom_alias,),
                ).fetchone()
                if alias_used:
                    raise AliasInUseError(custom_alias)
                short_code = custom_alias
            else:
                short_code = None
                for _ in range(12):
                    candidate = self._new_code()
                    collision = conn.execute(
                        "SELECT 1 FROM links WHERE short_code = ?",
                        (candidate,),
                    ).fetchone()
                    if not collision:
                        short_code = candidate
                        break
                if not short_code:
                    raise RuntimeError("could not generate a unique short code")

            conn.execute(
                """
                INSERT INTO links(
                    original_url,
                    original_url_hash,
                    short_code,
                    created_by,
                    created_at,
                    expires_at,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    original_url,
                    url_hash,
                    short_code,
                    created_by,
                    now.isoformat(),
                    expires_at.isoformat() if expires_at else None,
                ),
            )

        return {
            "short_code": short_code,
            "original_url": original_url,
            "created_at": now,
            "expires_at": expires_at,
            "already_exists": False,
        }

    def resolve_link(self, short_code: str) -> str:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT original_url, expires_at, is_active
                FROM links
                WHERE short_code = ?
                """,
                (short_code,),
            ).fetchone()

        if not row or row["is_active"] == 0:
            raise LinkNotFoundError(short_code)

        expires_at = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
        if expires_at and expires_at < self._now():
            raise LinkExpiredError(short_code)

        return cast(str, row["original_url"])

    def record_click(
        self,
        short_code: str,
        referrer: Optional[str],
        user_agent: Optional[str],
        client_ip: Optional[str],
    ) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO clicks(short_code, clicked_at, referrer, user_agent, ip_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    short_code,
                    self._now().isoformat(),
                    referrer,
                    user_agent,
                    self._hash_ip(client_ip),
                ),
            )

    def get_link_details(self, short_code: str) -> dict:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT original_url, short_code, created_by, created_at, expires_at, is_active
                FROM links
                WHERE short_code = ?
                """,
                (short_code,),
            ).fetchone()
        if not row:
            raise LinkNotFoundError(short_code)
        return {
            "short_code": row["short_code"],
            "original_url": row["original_url"],
            "created_by": row["created_by"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "expires_at": datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            "is_active": bool(row["is_active"]),
        }

    def get_stats(self, short_code: str) -> dict:
        with self.db.connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM links WHERE short_code = ?",
                (short_code,),
            ).fetchone()
            if not exists:
                raise LinkNotFoundError(short_code)

            total = conn.execute(
                "SELECT COUNT(*) AS c FROM clicks WHERE short_code = ?",
                (short_code,),
            ).fetchone()["c"]
            unique_visitors = conn.execute(
                "SELECT COUNT(DISTINCT ip_hash) AS c FROM clicks WHERE short_code = ?",
                (short_code,),
            ).fetchone()["c"]
            ref_rows = conn.execute(
                """
                SELECT referrer, COUNT(*) AS c
                FROM clicks
                WHERE short_code = ? AND referrer IS NOT NULL AND referrer != ''
                GROUP BY referrer
                ORDER BY c DESC
                LIMIT 3
                """,
                (short_code,),
            ).fetchall()

        return {
            "short_code": short_code,
            "total_clicks": int(total),
            "unique_visitors": int(unique_visitors),
            "top_referrers": [r["referrer"] for r in ref_rows],
        }

    def deactivate(self, short_code: str) -> bool:
        with self.db.connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM links WHERE short_code = ?",
                (short_code,),
            ).fetchone()
            if not exists:
                raise LinkNotFoundError(short_code)
            conn.execute(
                "UPDATE links SET is_active = 0 WHERE short_code = ?",
                (short_code,),
            )
        return True

    def healthcheck(self) -> bool:
        with self.db.connection() as conn:
            conn.execute("SELECT 1")
        return True
