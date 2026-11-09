from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

MAX_SEEN_PER_USER = 2000


@dataclass(slots=True)
class UserRecord:
    city: str | None = None
    sphere: str | None = None
    running: bool = False
    seen: set[str] = field(default_factory=set)


class Storage:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._users: dict[int, UserRecord] = {}
        self._lock = asyncio.Lock()

    async def load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Не удалось прочитать %s: %s", self._path, exc)
            return

        users = payload.get("users", payload) if isinstance(payload, dict) else {}
        if not isinstance(users, dict):
            return

        for raw_id, raw_record in users.items():
            try:
                user_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if not isinstance(raw_record, dict):
                continue
            seen = raw_record.get("seen") or []
            if not isinstance(seen, list):
                seen = []
            record = UserRecord(
                city=raw_record.get("city") or None,
                sphere=raw_record.get("sphere") or None,
                running=bool(raw_record.get("running")),
                seen={str(url) for url in seen if url},
            )
            self._users[user_id] = record

        log.info("Загружено пользователей: %d", len(self._users))

    async def get(self, user_id: int) -> UserRecord:
        record = self._users.get(user_id)
        if record is None:
            record = UserRecord()
            self._users[user_id] = record
        return record

    async def update(self, user_id: int, **fields: object) -> UserRecord:
        async with self._lock:
            record = self._users.get(user_id)
            if record is None:
                record = UserRecord()
                self._users[user_id] = record
            for name, value in fields.items():
                if hasattr(record, name):
                    setattr(record, name, value)
            self._save()
            return record

    async def mark_seen(self, user_id: int, keys: list[str]) -> None:
        if not keys:
            return
        async with self._lock:
            record = self._users.get(user_id)
            if record is None:
                record = UserRecord()
                self._users[user_id] = record
            record.seen.update(keys)
            if len(record.seen) > MAX_SEEN_PER_USER:
                record.seen = set(sorted(record.seen)[-MAX_SEEN_PER_USER:])
            self._save()

    async def all_users(self) -> list[tuple[int, UserRecord]]:
        return list(self._users.items())

    def _save(self) -> None:
        payload = {
            "users": {
                str(user_id): {
                    "city": record.city,
                    "sphere": record.sphere,
                    "running": record.running,
                    "seen": sorted(record.seen),
                }
                for user_id, record in self._users.items()
            }
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, self._path)
        except OSError as exc:
            log.warning("Не удалось сохранить состояние: %s", exc)
