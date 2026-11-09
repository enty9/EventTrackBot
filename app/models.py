from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Event:
    title: str
    url: str
    source: str
    official_url: str = ""
    description: str = ""
    start: datetime | None = None
    end: datetime | None = None
    city: str = ""
    venue: str = ""
    address: str = ""
    price: float | None = None
    currency: str = ""
    price_rub: float | None = None
    price_from: bool = False
    image: str = ""
    organizer: str = ""
    age: str = ""
    is_free: bool | None = None
    registration_url: str = ""
    event_type: str = ""
    attendance: str = ""
    page_url: str = field(default="", repr=False, compare=False)
    page_text: str = field(default="", repr=False, compare=False)

    @property
    def key(self) -> str:
        start = self.start.isoformat(timespec="minutes") if self.start else ""
        raw = f"{self.title.strip().lower()}|{start}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
