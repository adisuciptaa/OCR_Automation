"""SQLite persistence adapter for publisher identities, public keys, and trust audit."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.feature_manager.models import PublisherKeyRecord, PublisherRecord, PublisherStatus


class SQLitePublisherTrustRepository:
    def __init__(self, database_path: Path | str, migration_path: Path | None = None) -> None:
        self._path = Path(database_path)
        self._migration_path = migration_path or Path(__file__).parents[1] / "migrations" / "0004_publisher_trust.sql"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(self._migration_path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def get_publisher(self, publisher_id: str) -> PublisherRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM publisher_registry WHERE publisher_id=?", (publisher_id,)).fetchone()
        return self._publisher(row) if row else None

    def list_publishers(self) -> tuple[PublisherRecord, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT * FROM publisher_registry ORDER BY publisher_id").fetchall()
        return tuple(self._publisher(row) for row in rows)

    def register_publisher(self, publisher: PublisherRecord, key: PublisherKeyRecord) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO publisher_registry VALUES (?, ?, ?, ?, ?, ?)",
                (publisher.publisher_id, publisher.display_name, publisher.status.value,
                 publisher.created_at.isoformat(), publisher.updated_at.isoformat(),
                 publisher.revoked_at.isoformat() if publisher.revoked_at else None),
            )
            connection.execute(
                "INSERT INTO publisher_keys VALUES (?, ?, ?, ?, ?, ?)",
                (key.publisher_id, key.key_id, key.public_key_b64, key.status,
                 key.created_at.isoformat(), key.revoked_at.isoformat() if key.revoked_at else None),
            )

    def add_key(self, key: PublisherKeyRecord) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO publisher_keys VALUES (?, ?, ?, ?, ?, ?)",
                (key.publisher_id, key.key_id, key.public_key_b64, key.status,
                 key.created_at.isoformat(), key.revoked_at.isoformat() if key.revoked_at else None),
            )

    def get_key(self, publisher_id: str, key_id: str) -> PublisherKeyRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM publisher_keys WHERE publisher_id=? AND key_id=?",
                (publisher_id, key_id),
            ).fetchone()
        return self._key(row) if row else None

    def list_keys(self, publisher_id: str) -> tuple[PublisherKeyRecord, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM publisher_keys WHERE publisher_id=? ORDER BY created_at",
                (publisher_id,),
            ).fetchall()
        return tuple(self._key(row) for row in rows)

    def revoke_publisher(self, publisher_id: str, now: datetime) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE publisher_registry SET status='revoked', updated_at=?, revoked_at=? WHERE publisher_id=?",
                (now.isoformat(), now.isoformat(), publisher_id),
            )
            connection.execute(
                "UPDATE publisher_keys SET status='revoked', revoked_at=? WHERE publisher_id=?",
                (now.isoformat(), publisher_id),
            )

    def revoke_key(self, publisher_id: str, key_id: str, now: datetime) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE publisher_keys SET status='revoked', revoked_at=? WHERE publisher_id=? AND key_id=?",
                (now.isoformat(), publisher_id, key_id),
            )

    def audit(self, *, actor_id: str, publisher_id: str, action: str,
              outcome: str, details: dict[str, object] | None = None) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO publisher_trust_audit VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid4()), actor_id, publisher_id, action, outcome,
                 json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                 datetime.now(UTC).isoformat()),
            )

    @staticmethod
    def _publisher(row: sqlite3.Row) -> PublisherRecord:
        return PublisherRecord(
            row["publisher_id"], row["display_name"], PublisherStatus(row["status"]),
            datetime.fromisoformat(row["created_at"]), datetime.fromisoformat(row["updated_at"]),
            datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
        )

    @staticmethod
    def _key(row: sqlite3.Row) -> PublisherKeyRecord:
        return PublisherKeyRecord(
            row["publisher_id"], row["key_id"], row["public_key_b64"], row["status"],
            datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["revoked_at"]) if row["revoked_at"] else None,
        )
