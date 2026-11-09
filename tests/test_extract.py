from __future__ import annotations

import unittest

from app.search.extract import extract_events

JSON_LD_HTML = """
<html><head><title>Python Meetup</title></head><body>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BusinessEvent",
  "name": "Python Meetup для разработчиков",
  "startDate": "2026-05-12T18:30:00+03:00",
  "endDate": "2026-05-12T21:00:00+03:00",
  "description": "Встреча разработчиков на Python.",
  "image": "/images/poster.jpg",
  "location": {
    "@type": "Place",
    "name": "Крокус Экспо",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "Москва",
      "streetAddress": "МКАД, 66 км",
      "postalCode": "143402"
    }
  },
  "offers": {
    "@type": "Offer",
    "price": "1500",
    "priceCurrency": "RUB",
    "url": "https://example.com/reg"
  },
  "organizer": {"@type": "Organization", "name": "IT Community"},
  "typicalAgeRatingFrom": "18"
}
</script>
</body></html>
"""

FALLBACK_HTML = """
<html><head>
<title>Конференция разработчиков</title>
<meta property="og:title" content="Конференция разработчиков">
<meta property="og:description" content="Большая конференция по программированию.">
<meta property="og:image" content="https://example.org/poster.png">
</head><body>
<h1>Конференция разработчиков</h1>
<time datetime="2026-06-01">1 июня</time>
<p>Регистрация на мероприятие открыта. Стоимость 900 руб.</p>
</body></html>
"""


class ExtractTests(unittest.TestCase):
    def test_jsonld_event(self) -> None:
        events = extract_events(JSON_LD_HTML, "https://example.com/events/python")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.title, "Python Meetup для разработчиков")
        self.assertEqual(event.city, "Москва")
        self.assertEqual(event.venue, "Крокус Экспо")
        self.assertIn("МКАД", event.address)
        self.assertEqual(event.price, 1500.0)
        self.assertEqual(event.currency, "RUB")
        self.assertFalse(event.is_free)
        self.assertEqual(event.image, "https://example.com/images/poster.jpg")
        self.assertEqual(event.registration_url, "https://example.com/reg")
        self.assertEqual(event.organizer, "IT Community")
        self.assertEqual(event.age, "18+")
        self.assertEqual(event.source, "example.com")

    def test_fallback_event(self) -> None:
        events = extract_events(FALLBACK_HTML, "https://example.org/conf")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.title, "Конференция разработчиков")
        self.assertEqual(event.start.year, 2026)
        self.assertEqual(event.start.month, 6)
        self.assertEqual(event.start.day, 1)
        self.assertEqual(event.price, 900.0)
        self.assertEqual(event.image, "https://example.org/poster.png")

    def test_official_url_keeps_source_page(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@type": "Event", "name": "Митап", "startDate": "2026-07-01",
         "url": "https://t.me/hackathons/1",
         "location": {"@type": "Place", "address": {"addressLocality": "Москва"}}}
        </script>
        """
        events = extract_events(html, "https://hacklist.ru/itevents/meetup/")
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.source, "hacklist.ru")
        self.assertEqual(event.url, "https://hacklist.ru/itevents/meetup/")
        self.assertEqual(event.official_url, "https://t.me/hackathons/1")

    def test_event_key_is_unique_per_date(self) -> None:
        first = extract_events(
            '<script type="application/ld+json">'
            '{"@type":"Event","name":"Митап","startDate":"2026-07-01"}'
            "</script>",
            "https://example.com/a",
        )[0]
        second = extract_events(
            '<script type="application/ld+json">'
            '{"@type":"Event","name":"Митап","startDate":"2026-08-01"}'
            "</script>",
            "https://example.com/b",
        )[0]
        self.assertNotEqual(first.key, second.key)

    def test_free_event_has_zero_price(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@type": "Event", "name": "Бесплатный митап", "startDate": "2026-07-01",
         "isAccessibleForFree": true,
         "location": {"@type": "Place", "address": {"addressLocality": "Казань"}}}
        </script>
        """
        events = extract_events(html, "https://example.com/free")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].price, 0.0)
        self.assertTrue(events[0].is_free)


if __name__ == "__main__":
    unittest.main()
