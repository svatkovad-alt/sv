#!/usr/bin/env python3
"""
Daily Energy Law Watch — головний раннер.

Запускає повний цикл: скрапінг → фільтрація → дедуплікація → збагачення →
генерація звіту → оновлення логу.

Використання:
    python execution/run_energy_watch.py              # одноразовий запуск
    python execution/run_energy_watch.py --no-ai      # без AI-аналізу
    python execution/run_energy_watch.py --daemon      # демон (щоденно о 08:30)
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Додати execution/ до шляху імпорту
sys.path.insert(0, str(Path(__file__).resolve().parent))

from energy_watch_config import DATA_DIR, DIGESTS_DIR
from energy_watch_filter import filter_relevant
from energy_watch_log import add_to_log, deduplicate_items, load_log
from energy_watch_report import compile_full_report, save_report
from energy_watch_scraper import enrich_items, scrape_all_sources

# --- Логування ---
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


def setup_logging(verbose: bool = False) -> None:
    """Налаштувати логування."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)
    # Файловий хендлер
    file_handler = logging.FileHandler(DATA_DIR / "energy_watch.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    file_handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(file_handler)


logger = logging.getLogger("energy_watch.runner")


def run_daily_cycle(use_ai: bool = True) -> Path:
    """Виконати повний щоденний цикл.

    Повертає шлях до згенерованого звіту.
    """
    run_date = datetime.now().strftime("%Y-%m-%d")
    logger.info("=" * 60)
    logger.info("Starting daily energy watch cycle for %s", run_date)
    logger.info("=" * 60)

    # Крок 1: Завантажити лог
    logger.info("Step 1: Loading processed log...")
    log_entries = load_log()

    # Крок 2: Скрапити всі джерела
    logger.info("Step 2: Scraping all sources...")
    all_items = scrape_all_sources()

    if not all_items:
        logger.warning("No items scraped from any source. Check connectivity and selectors.")
        # Все одно створити порожній звіт
        report = compile_full_report([], run_date, use_ai=False)
        report_path = save_report(report, run_date)
        logger.info("Empty report saved to %s", report_path)
        return report_path

    # Крок 3: Фільтрація за релевантністю
    logger.info("Step 3: Filtering by relevance...")
    relevant, skipped = filter_relevant(all_items)

    # Крок 4: Дедуплікація
    logger.info("Step 4: Deduplicating against log...")
    new_items, already_processed = deduplicate_items(relevant, log_entries)

    logger.info(
        "Summary: %d total scraped → %d relevant → %d new (after dedup), %d skipped, %d already processed",
        len(all_items), len(relevant), len(new_items), len(skipped), len(already_processed),
    )

    # Крок 5: Збагачення (повний текст)
    logger.info("Step 5: Enriching items with full text...")
    enriched = enrich_items(new_items)

    # Крок 6: Генерація звіту
    logger.info("Step 6: Generating report (AI=%s)...", use_ai)
    report = compile_full_report(enriched, run_date, use_ai=use_ai)
    report_path = save_report(report, run_date)

    # Крок 7: Оновити лог
    logger.info("Step 7: Updating log...")
    add_to_log(enriched, status="processed")
    add_to_log(skipped, status="skipped", reason="irrelevant")

    logger.info("=" * 60)
    logger.info("Daily cycle complete. Report: %s", report_path)
    logger.info("Processed: %d items, Skipped: %d items", len(enriched), len(skipped))
    logger.info("=" * 60)

    return report_path


def run_daemon() -> None:
    """Запустити в режимі демона — щоденно о 08:30."""
    try:
        import schedule
        import time
    except ImportError:
        logger.error(
            "Package 'schedule' not installed. "
            "Run: pip install schedule"
        )
        sys.exit(1)

    logger.info("Starting daemon mode. Scheduled daily at 08:30.")

    schedule.every().day.at("08:30").do(run_daily_cycle)

    # Запустити одразу при старті
    logger.info("Running initial cycle now...")
    run_daily_cycle()

    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser(
        description="Daily Energy Law Watch — моніторинг енергетичного законодавства України"
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Вимкнути AI-аналіз (тільки скрапінг та фільтрація)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Запустити в режимі демона (щоденно о 08:30)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Детальне логування (DEBUG рівень)",
    )
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    if args.daemon:
        run_daemon()
    else:
        report_path = run_daily_cycle(use_ai=not args.no_ai)
        print(f"\nЗвіт збережено: {report_path}")


if __name__ == "__main__":
    main()
