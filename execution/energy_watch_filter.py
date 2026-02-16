"""
Модуль фільтрації публікацій за релевантністю.
Використовує ключові слова з конфігурації для скорингу.
"""

import logging
import re

from energy_watch_config import (
    PRIMARY_KEYWORDS,
    RELEVANCE_THRESHOLD_PRIMARY,
    RELEVANCE_THRESHOLD_SECONDARY,
    SECONDARY_KEYWORDS,
)

logger = logging.getLogger("energy_watch.filter")


def _normalize(text: str) -> str:
    """Нормалізувати текст для пошуку ключових слів."""
    return text.lower().strip()


def _count_keyword_matches(text: str, keywords: list[str]) -> tuple[int, list[str]]:
    """Порахувати кількість збігів ключових слів у тексті.

    Повертає (кількість, список знайдених слів).
    """
    text_lower = _normalize(text)
    matches = []
    for kw in keywords:
        # Використовуємо word boundary де можливо, але для кирилиці
        # простий пошук підрядка є надійнішим
        if _normalize(kw) in text_lower:
            matches.append(kw)
    return len(matches), matches


def score_relevance(item: dict) -> dict:
    """Оцінити релевантність публікації.

    Додає до item:
      - relevance_score: числовий скор (0 = нерелевантний)
      - relevance_primary: список знайдених основних ключових слів
      - relevance_secondary: список знайдених додаткових ключових слів
      - is_relevant: bool
    """
    # Обʼєднати заголовок і текст для пошуку
    searchable = f"{item.get('title', '')} {item.get('full_text', '')}"

    primary_count, primary_matches = _count_keyword_matches(searchable, PRIMARY_KEYWORDS)
    secondary_count, secondary_matches = _count_keyword_matches(searchable, SECONDARY_KEYWORDS)

    # Скоринг: primary × 3 + secondary × 1
    score = primary_count * 3 + secondary_count

    # Релевантність: є основне слово, АБО достатньо додаткових
    is_relevant = (
        primary_count >= RELEVANCE_THRESHOLD_PRIMARY
        or secondary_count >= RELEVANCE_THRESHOLD_SECONDARY
    )

    # Джерела MEV та NERC завжди релевантні (профільні органи)
    if item.get("source_id") in ("mev", "nerc"):
        is_relevant = True
        score = max(score, 3)

    item["relevance_score"] = score
    item["relevance_primary"] = primary_matches
    item["relevance_secondary"] = secondary_matches
    item["is_relevant"] = is_relevant

    return item


def filter_relevant(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Відфільтрувати список публікацій на релевантні та пропущені.

    Повертає (relevant, skipped).
    Релевантні відсортовані за score (спадання).
    """
    relevant = []
    skipped = []

    for item in items:
        scored = score_relevance(item)
        if scored["is_relevant"]:
            relevant.append(scored)
        else:
            scored["skip_reason"] = "Не знайдено релевантних ключових слів"
            skipped.append(scored)

    # Сортувати за релевантністю (найважливіші першими)
    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)

    logger.info(
        "Filtering: %d relevant, %d skipped out of %d total",
        len(relevant), len(skipped), len(items),
    )
    return relevant, skipped
