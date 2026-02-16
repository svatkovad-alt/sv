"""
Веб-скрапер для всіх 7 офіційних джерел.
Кожне джерело має свою функцію-скрапер та загальні fallback-механізми.

Повертає список словників (PublicationItem) для кожного джерела.
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from energy_watch_config import (
    HEADERS,
    LOOKBACK_DELTA,
    MAX_RETRIES,
    RAW_PAGES_DIR,
    REQUEST_TIMEOUT,
    RETRY_DELAY,
    SOURCES,
)

logger = logging.getLogger("energy_watch.scraper")

# Часова зона Києва (UTC+2 / UTC+3 влітку)
UA_TZ = timezone(timedelta(hours=2))


def make_publication_item(
    source_id: str,
    title: str,
    url: str,
    published_date: Optional[datetime],
    pub_type: str = "новина",
    full_text: str = "",
    unique_id: str = "",
) -> dict:
    """Створити стандартизований словник публікації."""
    if not unique_id:
        unique_id = hashlib.md5(url.encode()).hexdigest()[:12]
    return {
        "source_id": source_id,
        "source_name": SOURCES.get(source_id, {}).get("name", source_id),
        "source_short": SOURCES.get(source_id, {}).get("short_name", source_id),
        "title": title.strip() if title else "",
        "url": url.strip(),
        "published_date": published_date,
        "type": pub_type,
        "full_text": full_text.strip() if full_text else "",
        "unique_id": unique_id,
    }


# --- HTTP-утиліти ---

def fetch_page(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
    """Завантажити HTML-сторінку з ретраями."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, verify=True)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except requests.RequestException as e:
            logger.warning("Fetch attempt %d/%d failed for %s: %s",
                           attempt + 1, MAX_RETRIES + 1, url, e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
    logger.error("Failed to fetch %s after %d attempts", url, MAX_RETRIES + 1)
    return None


def cache_page(source_id: str, url: str, html: str) -> None:
    """Зберегти HTML у tmp/ для дебагу."""
    safe_name = re.sub(r'[^\w\-.]', '_', urlparse(url).path)[:80]
    path = RAW_PAGES_DIR / f"{source_id}_{safe_name}.html"
    path.write_text(html, encoding="utf-8")


def parse_date(text: str, formats: list[str]) -> Optional[datetime]:
    """Спробувати розпарсити дату з кількох форматів."""
    if not text:
        return None
    text = text.strip()
    # ISO datetime з timezone
    if "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            pass
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=UA_TZ)
        except ValueError:
            continue
    logger.debug("Could not parse date: '%s'", text)
    return None


def extract_date_from_soup(soup: BeautifulSoup, selectors: list[str],
                           date_formats: list[str]) -> Optional[datetime]:
    """Спробувати витягнути дату за допомогою списку CSS-селекторів."""
    for sel in selectors:
        el = soup.select_one(sel)
        if not el:
            continue
        # Спочатку перевірити атрибут datetime
        dt_attr = el.get("datetime")
        if dt_attr:
            parsed = parse_date(dt_attr, date_formats)
            if parsed:
                return parsed
        # Потім текстовий вміст
        parsed = parse_date(el.get_text(strip=True), date_formats)
        if parsed:
            return parsed
    return None


def extract_text_from_soup(soup: BeautifulSoup, selectors: list[str]) -> str:
    """Витягнути текст за допомогою списку CSS-селекторів (перший що спрацює)."""
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            # Видалити скрипти та стилі
            for tag in el.find_all(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 50:  # мінімальна довжина корисного тексту
                return text
    return ""


def is_within_lookback(pub_date: Optional[datetime], now: datetime) -> bool:
    """Перевірити чи публікація потрапляє у вікно перевірки."""
    if pub_date is None:
        return True  # якщо дату не вдалось визначити — включити
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=UA_TZ)
    return (now - pub_date) <= LOOKBACK_DELTA


def classify_publication_type(title: str, url: str, text: str) -> str:
    """Визначити тип публікації за ключовими словами в заголовку/URL."""
    combined = (title + " " + url + " " + text[:500]).lower()
    if any(w in combined for w in ["законопроєкт", "законопроект", "проект закону"]):
        return "законопроєкт"
    if any(w in combined for w in ["закон україни", "прийнято закон"]):
        return "закон"
    if any(w in combined for w in ["постанова"]):
        return "постанова"
    if any(w in combined for w in ["розпорядження"]):
        return "розпорядження"
    if any(w in combined for w in ["наказ"]):
        return "наказ"
    if any(w in combined for w in ["роз'яснення", "розяснення", "консультація"]):
        return "роз'яснення"
    if any(w in combined for w in ["рішення"]):
        return "рішення"
    return "новина"


# --- Скрапери для окремих джерел ---

def scrape_generic_news(source_id: str) -> list[dict]:
    """Загальний скрапер для стандартних новинних сторінок (Rada, MEV, DIAM, Tax, NERC)."""
    src = SOURCES[source_id]
    now = datetime.now(UA_TZ)
    results = []
    seen_urls = set()

    for news_url in src["news_urls"]:
        html = fetch_page(news_url)
        if not html:
            continue
        cache_page(source_id, news_url, html)
        soup = BeautifulSoup(html, "lxml")

        # Спробувати знайти посилання на статті
        links = []
        for sel in src["selectors"].get("article_list", []):
            found = soup.select(sel)
            if found:
                links.extend(found)
                break  # використати перший селектор що спрацював

        if not links:
            # Fallback: шукати всі посилання з ключовими словами в href
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(p in href for p in ["/news/", "/novyny/", "/npas/", "/acts/",
                                           "/media-tsentr/", "/content/"]):
                    links.append(a)

        for link_el in links:
            href = link_el.get("href", "")
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue

            full_url = urljoin(src["base_url"], href)

            # Уникнути дублікатів на сторінці
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            title = link_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Спробувати витягнути дату з батьківського елемента
            parent = link_el.parent
            pub_date = None
            if parent:
                pub_date = extract_date_from_soup(
                    parent, src["selectors"].get("date", []), src["date_formats"]
                )

            if not is_within_lookback(pub_date, now):
                continue

            results.append(make_publication_item(
                source_id=source_id,
                title=title,
                url=full_url,
                published_date=pub_date,
            ))

    logger.info("Source '%s': found %d candidate links", source_id, len(results))
    return results


def fetch_full_article(item: dict) -> dict:
    """Завантажити повний текст статті та оновити item."""
    src = SOURCES.get(item["source_id"], {})
    html = fetch_page(item["url"])
    if not html:
        return item

    soup = BeautifulSoup(html, "lxml")

    # Оновити заголовок якщо є кращий
    for sel in src.get("selectors", {}).get("title", ["h1"]):
        el = soup.select_one(sel)
        if el:
            better_title = el.get_text(strip=True)
            if better_title and len(better_title) > len(item["title"]):
                item["title"] = better_title
            break

    # Оновити дату якщо не було
    if item["published_date"] is None:
        item["published_date"] = extract_date_from_soup(
            soup,
            src.get("selectors", {}).get("date", ["time[datetime]"]),
            src.get("date_formats", ["%d.%m.%Y"]),
        )

    # Витягнути повний текст
    item["full_text"] = extract_text_from_soup(
        soup,
        src.get("selectors", {}).get("body", ["article .content", ".content"]),
    )

    # Класифікувати тип
    item["type"] = classify_publication_type(item["title"], item["url"], item["full_text"])

    return item


def scrape_kmu() -> list[dict]:
    """Скрапер для KMU — спочатку RSS, потім HTML fallback."""
    src = SOURCES["kmu"]
    now = datetime.now(UA_TZ)
    results = []
    seen_urls = set()

    # Спробувати RSS
    if src.get("rss_url"):
        try:
            feed = feedparser.parse(src["rss_url"])
            for entry in feed.entries:
                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title = entry.get("title", "")
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=UA_TZ)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_date = datetime(*entry.updated_parsed[:6], tzinfo=UA_TZ)

                if not is_within_lookback(pub_date, now):
                    continue

                summary = entry.get("summary", "")
                results.append(make_publication_item(
                    source_id="kmu",
                    title=title,
                    url=url,
                    published_date=pub_date,
                    full_text=BeautifulSoup(summary, "lxml").get_text() if summary else "",
                ))

            if results:
                logger.info("KMU RSS: found %d items", len(results))
                return results
        except Exception as e:
            logger.warning("KMU RSS failed, falling back to HTML: %s", e)

    # HTML fallback
    return scrape_generic_news("kmu")


def scrape_telegram_vru() -> list[dict]:
    """Скрапер для Telegram-каналу ВРУ через веб-превʼю."""
    src = SOURCES["telegram_vru"]
    now = datetime.now(UA_TZ)
    results = []

    html = fetch_page(src["news_urls"][0])
    if not html:
        return results

    cache_page("telegram_vru", src["news_urls"][0], html)
    soup = BeautifulSoup(html, "lxml")

    # Telegram web preview: кожне повідомлення у .tgme_widget_message_wrap
    message_selectors = src["selectors"].get("message", [])
    messages = []
    for sel in message_selectors:
        found = soup.select(sel)
        if found:
            messages = found
            break

    for msg in messages:
        # Текст повідомлення
        text = ""
        for sel in src["selectors"].get("message_text", []):
            el = msg.select_one(sel)
            if el:
                text = el.get_text(separator="\n", strip=True)
                break

        if not text or len(text) < 20:
            continue

        # Дата
        pub_date = None
        for sel in src["selectors"].get("message_date", []):
            el = msg.select_one(sel)
            if el:
                dt_attr = el.get("datetime")
                if dt_attr:
                    pub_date = parse_date(dt_attr, src["date_formats"])
                break

        if not is_within_lookback(pub_date, now):
            continue

        # Посилання на повідомлення
        msg_url = ""
        for sel in src["selectors"].get("message_link", []):
            el = msg.select_one(sel)
            if el and el.get("href"):
                msg_url = el["href"]
                if not msg_url.startswith("http"):
                    msg_url = "https://t.me" + msg_url
                break

        # Заголовок — перші 100 символів тексту
        title = text[:100].split("\n")[0]
        if len(title) > 80:
            title = title[:77] + "..."

        results.append(make_publication_item(
            source_id="telegram_vru",
            title=title,
            url=msg_url,
            published_date=pub_date,
            full_text=text,
            pub_type="повідомлення",
        ))

    logger.info("Telegram VRU: found %d messages", len(results))
    return results


# --- Головний інтерфейс ---

def scrape_all_sources() -> list[dict]:
    """Скрапити всі джерела та повернути обʼєднаний список публікацій."""
    all_items = []

    # Джерела зі стандартним скрапером
    standard_sources = ["rada", "mev", "diam", "tax", "nerc"]
    for source_id in standard_sources:
        try:
            items = scrape_generic_news(source_id)
            all_items.extend(items)
        except Exception as e:
            logger.error("Error scraping %s: %s", source_id, e, exc_info=True)

    # KMU (RSS + fallback)
    try:
        all_items.extend(scrape_kmu())
    except Exception as e:
        logger.error("Error scraping KMU: %s", e, exc_info=True)

    # Telegram
    try:
        all_items.extend(scrape_telegram_vru())
    except Exception as e:
        logger.error("Error scraping Telegram VRU: %s", e, exc_info=True)

    logger.info("Total scraped items across all sources: %d", len(all_items))
    return all_items


def enrich_items(items: list[dict]) -> list[dict]:
    """Завантажити повний текст для кожного item (крім Telegram — вже є)."""
    enriched = []
    for item in items:
        if item["source_id"] == "telegram_vru":
            enriched.append(item)
            continue
        try:
            enriched.append(fetch_full_article(item))
        except Exception as e:
            logger.warning("Error enriching %s: %s", item["url"], e)
            enriched.append(item)
        # Невелика пауза між запитами
        time.sleep(0.5)
    return enriched
