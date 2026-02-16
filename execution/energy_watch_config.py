"""
Конфігурація для Daily Energy Law Watch.
Джерела, ключові слова, шляхи, CSS-селектори.
"""

import os
from pathlib import Path
from datetime import timedelta

# --- Шляхи ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DIGESTS_DIR = DATA_DIR / "digests"
TMP_DIR = PROJECT_ROOT / "tmp"
RAW_PAGES_DIR = TMP_DIR / "raw_pages"
LOG_FILE = DATA_DIR / "processed_log.csv"
ENV_FILE = PROJECT_ROOT / ".env"

# Створити директорії якщо не існують
for d in [DATA_DIR, DIGESTS_DIR, TMP_DIR, RAW_PAGES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- HTTP ---
REQUEST_TIMEOUT = 30  # секунд
MAX_RETRIES = 2
RETRY_DELAY = 3  # секунд
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# --- Часове вікно ---
LOOKBACK_HOURS = 72  # перевіряти публікації за останні N годин
LOOKBACK_DELTA = timedelta(hours=LOOKBACK_HOURS)

# --- Джерела ---
# Кожне джерело має: id, name, base_url, news_urls (сторінки для скрапінгу),
# rss_url (якщо є), та selectors (CSS-селектори для парсингу).
SOURCES = {
    "rada": {
        "id": "rada",
        "name": "Верховна Рада України",
        "short_name": "Rada",
        "base_url": "https://www.rada.gov.ua",
        "news_urls": [
            "https://www.rada.gov.ua/news/razom",
            "https://www.rada.gov.ua/news/Novyny",
        ],
        "rss_url": None,
        "selectors": {
            # Список новин на сторінці
            "article_list": [
                ".news_list .news_item a",
                ".view-content .views-row a",
                "#block-system-main .item-list li a",
            ],
            # Заголовок статті
            "title": [
                "h1.page_title",
                "h1.title",
                "h1",
            ],
            # Дата публікації
            "date": [
                ".news_date",
                ".field-name-field-date .date-display-single",
                "time[datetime]",
                ".submitted",
            ],
            # Основний текст
            "body": [
                ".news_text",
                ".field-name-body .field-item",
                "#block-system-main .content",
                "article .content",
            ],
        },
        "date_formats": ["%d.%m.%Y", "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M:%S"],
    },
    "kmu": {
        "id": "kmu",
        "name": "Кабінет Міністрів України",
        "short_name": "KMU",
        "base_url": "https://www.kmu.gov.ua",
        "news_urls": [
            "https://www.kmu.gov.ua/news",
            "https://www.kmu.gov.ua/npas",
        ],
        "rss_url": "https://www.kmu.gov.ua/rss",
        "selectors": {
            "article_list": [
                ".news-list .item-title a",
                ".views-row .field-content a",
                ".item-list h3 a",
                "article h2 a",
            ],
            "title": [
                "h1.page-title",
                "h1.entry-title",
                "h1",
            ],
            "date": [
                ".field--name-created time",
                ".news-date",
                "time[datetime]",
                ".date-display-single",
            ],
            "body": [
                ".field--name-body .field__item",
                ".node__content .field--type-text-with-summary",
                "article .content",
                ".entry-content",
            ],
        },
        "date_formats": ["%d.%m.%Y", "%d %B %Y", "%Y-%m-%dT%H:%M:%S"],
    },
    "mev": {
        "id": "mev",
        "name": "Міністерство енергетики України",
        "short_name": "MEV",
        "base_url": "https://mev.gov.ua",
        "news_urls": [
            "https://mev.gov.ua/novyny",
        ],
        "rss_url": None,
        "selectors": {
            "article_list": [
                ".news-list a",
                ".view-content .views-row a",
                ".item-list li a",
                "article h2 a",
                ".card a",
            ],
            "title": ["h1.page-title", "h1", ".page-header h1"],
            "date": [
                ".news-date",
                "time[datetime]",
                ".date",
                ".field-name-field-date",
            ],
            "body": [
                ".field--name-body .field__item",
                ".node__content",
                "article .content",
                ".page-content",
            ],
        },
        "date_formats": ["%d.%m.%Y", "%d.%m.%Y %H:%M"],
    },
    "diam": {
        "id": "diam",
        "name": "ДІАМ (Держ. інспекція архітектури та містобудування)",
        "short_name": "DIAM",
        "base_url": "https://diam.gov.ua",
        "news_urls": [
            "https://diam.gov.ua/news",
            "https://diam.gov.ua/content/novyny",
        ],
        "rss_url": None,
        "selectors": {
            "article_list": [
                ".news-list a",
                ".view-content .views-row a",
                ".item-list li a",
                "article h2 a",
            ],
            "title": ["h1.page-title", "h1", ".news-title"],
            "date": [
                ".news-date",
                "time[datetime]",
                ".date",
            ],
            "body": [
                ".field--name-body .field__item",
                ".node__content",
                "article .content",
                ".news-body",
            ],
        },
        "date_formats": ["%d.%m.%Y", "%d.%m.%Y %H:%M"],
    },
    "tax": {
        "id": "tax",
        "name": "Державна податкова служба України",
        "short_name": "Tax",
        "base_url": "https://tax.gov.ua",
        "news_urls": [
            "https://tax.gov.ua/media-tsentr/novini/",
        ],
        "rss_url": None,
        "selectors": {
            "article_list": [
                ".newsblock a",
                ".news_item a",
                ".item-list li a",
                ".view-content a",
                "table.items td a",
            ],
            "title": ["h1", ".news-title h1", ".page-title"],
            "date": [
                ".newsblock .date",
                ".news-date",
                ".date",
                "time",
            ],
            "body": [
                ".newsblock .text",
                ".news-text",
                ".field-name-body",
                "#content .content",
                ".page-content",
            ],
        },
        "date_formats": ["%d.%m.%Y", "%d.%m.%Y %H:%M", "%d %B %Y"],
    },
    "telegram_vru": {
        "id": "telegram_vru",
        "name": "Telegram Верховної Ради",
        "short_name": "Telegram VRU",
        "base_url": "https://t.me",
        "news_urls": [
            "https://t.me/s/verkhovnaradaukrainy",
        ],
        "rss_url": None,
        "selectors": {
            # Telegram web preview має специфічну структуру
            "message": [
                ".tgme_widget_message_wrap",
                ".tgme_widget_message",
            ],
            "message_text": [
                ".tgme_widget_message_text",
                ".js-message_text",
            ],
            "message_date": [
                ".tgme_widget_message_date time",
                "time[datetime]",
            ],
            "message_link": [
                ".tgme_widget_message_date",
            ],
        },
        "date_formats": ["%Y-%m-%dT%H:%M:%S"],
    },
    "nerc": {
        "id": "nerc",
        "name": "НКРЕКП (Нац. комісія регулювання енергетики)",
        "short_name": "NERC",
        "base_url": "https://www.nerc.gov.ua",
        "news_urls": [
            "https://www.nerc.gov.ua/news",
            "https://www.nerc.gov.ua/acts",
        ],
        "rss_url": None,
        "selectors": {
            "article_list": [
                ".news-list a",
                ".view-content .views-row a",
                ".item-list li a",
                "article h2 a",
                ".card-title a",
                "table td a",
            ],
            "title": ["h1.page-title", "h1", ".news-title"],
            "date": [
                ".news-date",
                "time[datetime]",
                ".date",
                ".field-name-field-date",
            ],
            "body": [
                ".field--name-body .field__item",
                ".node__content",
                "article .content",
                ".page-content",
            ],
        },
        "date_formats": ["%d.%m.%Y", "%d.%m.%Y %H:%M"],
    },
}

# --- Ключові слова для фільтрації ---
# Основні (висока релевантність)
PRIMARY_KEYWORDS = [
    "енергетика",
    "електроенергія",
    "ринок електроенергії",
    "НКРЕКП",
    "тариф",
    "балансування",
    "гарантований покупець",
    "ВДЕ",
    "відновлювана енергетика",
    "зелений тариф",
    "аукціони",
    "ліцензія",
    "газ",
    "ГТС",
    "теплопостачання",
    "генерація",
    "розподіл",
    "приєднання",
    "технічні умови",
    "Укренерго",
    "оператор ринку",
]

# Додаткові (середня релевантність — потребують контексту)
SECONDARY_KEYWORDS = [
    "критична інфраструктура",
    "будівельні норми",
    "ДБН",
    "дозвільні процедури",
    "інспекція",
    "податки",
    "ПДВ",
    "акциз",
    "рента",
    "трансфертне ціноутворення",
    "енергоефективність",
    "сонячна",
    "вітрова",
    "біомаса",
    "когенерація",
    "електромережі",
    "облгаз",
    "обленерго",
    "нафтогаз",
    "енергоатом",
]

# Пороги релевантності: скільки збігів потрібно
RELEVANCE_THRESHOLD_PRIMARY = 1   # >= 1 основне ключове слово
RELEVANCE_THRESHOLD_SECONDARY = 2  # >= 2 додаткових (без основних)

# --- Anthropic API ---
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"
ANTHROPIC_MAX_TOKENS = 4096

# --- Лог ---
LOG_COLUMNS = [
    "date_processed",
    "source",
    "title",
    "url",
    "published_date",
    "unique_id",
    "status",
    "reason",
]
