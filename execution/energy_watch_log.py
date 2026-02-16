"""
Управління логом оброблених публікацій.
Зберігає стан у CSV для дедуплікації між запусками.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path

from energy_watch_config import LOG_COLUMNS, LOG_FILE

logger = logging.getLogger("energy_watch.log")


def _ensure_log_exists() -> None:
    """Створити файл логу з заголовками якщо не існує."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(LOG_COLUMNS)
        logger.info("Created new log file: %s", LOG_FILE)


def load_log() -> list[dict]:
    """Завантажити лог з CSV."""
    _ensure_log_exists()
    rows = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    logger.info("Loaded %d entries from log", len(rows))
    return rows


def get_processed_identifiers(log_entries: list[dict]) -> set:
    """Отримати множину (url, unique_id) пар зі статусом 'processed'."""
    identifiers = set()
    for entry in log_entries:
        if entry.get("status") == "processed":
            if entry.get("url"):
                identifiers.add(("url", entry["url"]))
            if entry.get("unique_id"):
                identifiers.add(("uid", entry["unique_id"]))
    return identifiers


def is_already_processed(item: dict, processed_ids: set) -> bool:
    """Перевірити чи публікація вже оброблена."""
    if ("url", item.get("url", "")) in processed_ids:
        return True
    if ("uid", item.get("unique_id", "")) in processed_ids:
        return True
    return False


def deduplicate_items(items: list[dict], log_entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Видалити вже оброблені публікації зі списку.

    Повертає (new_items, already_processed).
    """
    processed_ids = get_processed_identifiers(log_entries)
    new_items = []
    already_processed = []

    for item in items:
        if is_already_processed(item, processed_ids):
            already_processed.append(item)
        else:
            new_items.append(item)

    logger.info(
        "Deduplication: %d new, %d already processed",
        len(new_items), len(already_processed),
    )
    return new_items, already_processed


def add_to_log(items: list[dict], status: str = "processed", reason: str = "") -> None:
    """Додати публікації до логу."""
    _ensure_log_exists()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for item in items:
            pub_date = ""
            if item.get("published_date"):
                pub_date = item["published_date"].strftime("%Y-%m-%d %H:%M")
            row = [
                now,                           # date_processed
                item.get("source_id", ""),      # source
                item.get("title", "")[:200],    # title (обрізати)
                item.get("url", ""),            # url
                pub_date,                       # published_date
                item.get("unique_id", ""),      # unique_id
                status,                         # status
                reason or item.get("skip_reason", ""),  # reason
            ]
            writer.writerow(row)

    logger.info("Added %d items to log with status '%s'", len(items), status)
