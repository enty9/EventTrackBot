from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.models import Event
from app.search.engine import EventSearcher
from app.spheres import DEFAULT_SPHERE, SPHERES_BY_KEY, get_sphere, sphere_title


class SphereTests(unittest.TestCase):
    def test_available_spheres(self) -> None:
        self.assertEqual(set(SPHERES_BY_KEY), {"it", "chess", "anime"})

    def test_default_is_it(self) -> None:
        self.assertEqual(get_sphere(None).key, DEFAULT_SPHERE)

    def test_title(self) -> None:
        self.assertIn("Шахматы", sphere_title("chess"))
        self.assertIn("Аниме", sphere_title("anime"))

    def test_keywords(self) -> None:
        self.assertTrue(get_sphere("chess").keywords.search("Шахматный турнир"))
        self.assertTrue(get_sphere("anime").keywords.search("Косплей-фестиваль"))
        self.assertFalse(get_sphere("anime").keywords.search("Хакатон разработчиков"))

    def test_queries_are_formatted(self) -> None:
        queries = EventSearcher(None)._queries("Казань", get_sphere("chess"))
        self.assertTrue(all("Казань" in query for query in queries))
        self.assertTrue(any("шахмат" in query.lower() for query in queries))


class RelevanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.searcher = EventSearcher(None)
        self.now = datetime.now(timezone.utc)
        self.start = self.now + timedelta(days=7)

    def make_event(self, title: str) -> Event:
        return Event(
            title=title,
            url="https://example.com/event",
            source="example.com",
            start=self.start,
            city="Казань",
        )

    def test_it_event_passes_for_it(self) -> None:
        event = self.make_event("Хакатон разработчиков")
        self.assertTrue(
            self.searcher._is_relevant(event, "Казань", self.now, get_sphere("it"))
        )

    def test_it_event_rejected_for_anime(self) -> None:
        event = self.make_event("Хакатон разработчиков")
        self.assertFalse(
            self.searcher._is_relevant(event, "Казань", self.now, get_sphere("anime"))
        )

    def test_anime_event_passes_for_anime(self) -> None:
        event = self.make_event("Аниме-фестиваль и косплей")
        self.assertTrue(
            self.searcher._is_relevant(event, "Казань", self.now, get_sphere("anime"))
        )

    def test_chess_event_passes_for_chess(self) -> None:
        event = self.make_event("Шахматный турнир на кубок города")
        self.assertTrue(
            self.searcher._is_relevant(event, "Казань", self.now, get_sphere("chess"))
        )


if __name__ == "__main__":
    unittest.main()
