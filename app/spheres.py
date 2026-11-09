from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_SPHERE = "it"


@dataclass(frozen=True, slots=True)
class Sphere:
    key: str
    title: str
    emoji: str
    description: str
    keywords: re.Pattern[str]
    queries: tuple[str, ...]
    direct: bool = False


SPHERES: tuple[Sphere, ...] = (
    Sphere(
        key="it",
        title="IT",
        emoji="💻",
        description="программирование, хакатоны, митапы",
        keywords=re.compile(
            r"программ|разработ|айти|\bIT\b|\bИТ\b|хакатон|hackathon|митап|meetup|"
            r"developer|devops|python|javascript|typescript|java\b|golang|"
            r"backend|frontend|fullstack|machine\s*learning|\bML\b|data\s*science|"
            r"нейросет|искусственн\w*\s+интеллект|робот|информационн\w*\s+технолог|"
            r"computer\s*science|кодинг|coding|\bкод(?:а|у|ом|е)?\b|воркшоп|workshop|олимпиад",
            re.IGNORECASE,
        ),
        queries=(
            "мероприятия программирование {city} {year}",
            "IT конференция {city} {year}",
            "хакатон {city} {year}",
            "митап разработчиков {city} {year}",
            "конференция программистов {city}",
            "site:timepad.ru {city} программирование",
            "site:kudago.com {city} программирование",
            "site:meetup.com {city} программирование",
        ),
        direct=True,
    ),
    Sphere(
        key="chess",
        title="Шахматы",
        emoji="♟️",
        description="турниры, клубы, соревнования",
        keywords=re.compile(
            r"шахмат|шахматы|\bchess\b|гроссмейстер|шахматн|\bблиц\b|\bрапид\b|"
            r"chess-results|этюд|дебют",
            re.IGNORECASE,
        ),
        queries=(
            "шахматы {city} {year}",
            "шахматный турнир {city} {year}",
            "турнир по шахматам {city} расписание",
            "шахматный клуб {city}",
            "шахматы соревнования {city}",
            "шахматная школа {city} турнир",
            "site:chess-results.com {city}",
            "site:timepad.ru {city} шахматы",
        ),
    ),
    Sphere(
        key="anime",
        title="Аниме",
        emoji="🌸",
        description="фестивали, конвенты, косплей",
        keywords=re.compile(
            r"аниме|\banime\b|манга|\bmanga\b|косплей|cosplay|отаку|otaku|"
            r"аниме-|анимекон|анимефест|анимешн",
            re.IGNORECASE,
        ),
        queries=(
            "аниме {city} {year}",
            "аниме конвент {city} {year}",
            "аниме-фестиваль {city} {year}",
            "аниме встреча {city}",
            "косплей {city} {year}",
            "аниме пати {city}",
            "site:timepad.ru {city} аниме",
            "site:kudago.com {city} аниме",
        ),
    ),
)

SPHERES_BY_KEY: dict[str, Sphere] = {sphere.key: sphere for sphere in SPHERES}


def get_sphere(key: str | None) -> Sphere:
    return SPHERES_BY_KEY.get(key or DEFAULT_SPHERE, SPHERES_BY_KEY[DEFAULT_SPHERE])


def sphere_title(key: str | None) -> str:
    sphere = get_sphere(key)
    return f"{sphere.emoji} {sphere.title}"
