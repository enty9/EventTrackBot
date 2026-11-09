from __future__ import annotations

import unittest
from datetime import datetime

from app.cities import city_variants, normalize_city
from app.formatting import format_caption, format_details, format_price
from app.models import Event
from app.timeutil import format_event_date, parse_date_text, parse_iso_datetime


class CitiesTests(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(normalize_city("  город москва "), "Москва")
        self.assertEqual(normalize_city("нижний  новгород"), "Нижний Новгород")
        self.assertEqual(normalize_city("ростов - на - дону"), "Ростов-на-Дону")

    def test_variants(self) -> None:
        self.assertIn("москве", city_variants("Москва"))
        self.assertIn("уфе", city_variants("Уфа"))
        self.assertIn("спб", city_variants("Санкт-Петербург"))


class TimeTests(unittest.TestCase):
    def test_parse_iso(self) -> None:
        parsed = parse_iso_datetime("2026-05-12T18:30:00+03:00")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.hour, 18)

    def test_parse_text(self) -> None:
        parsed = parse_date_text("Конференция 12 июня 2026 года")
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed.year, parsed.month, parsed.day), (2026, 6, 12))

    def test_format_date(self) -> None:
        text = format_event_date(datetime(2026, 5, 12, 18, 30))
        self.assertIn("Вт", text)
        self.assertIn("12 мая 2026", text)
        self.assertIn("18:30", text)


class FormattingTests(unittest.TestCase):
    def make_event(self, **kwargs) -> Event:
        defaults = {
            "title": "Хакатон <AI>",
            "url": "https://example.com/event",
            "source": "example.com",
            "start": datetime(2026, 5, 12, 18, 30),
        }
        defaults.update(kwargs)
        return Event(**defaults)

    def test_paid_price_in_rubles(self) -> None:
        event = self.make_event(price=100, currency="USD", price_rub=9000, price_from=True)
        self.assertEqual(format_price(event), "💵 от 9 000 ₽")

    def test_free_has_no_price(self) -> None:
        self.assertEqual(format_price(self.make_event(price=0)), "")
        self.assertEqual(format_price(self.make_event()), "")

    def test_caption_escapes_html(self) -> None:
        caption = format_caption(self.make_event())
        self.assertIn("&lt;AI&gt;", caption)
        self.assertNotIn("<AI>", caption)

    def test_details_contains_source_and_registration(self) -> None:
        event = self.make_event(description="Описание", registration_url="https://example.com/reg")
        details = format_details(event)
        self.assertIn("https://example.com/event", details)
        self.assertIn("https://example.com/reg", details)
        self.assertIn("Ограничения не указаны", details)


if __name__ == "__main__":
    unittest.main()
