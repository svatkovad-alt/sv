"""
Відправка звітів через Telegram Bot API.

Telegram обмежує повідомлення до 4096 символів, тому довгі звіти
розбиваються на частини. Підтримує Markdown форматування.
"""

import logging
import os
import re
import time

import requests
from dotenv import load_dotenv

from energy_watch_config import ENV_FILE

load_dotenv(ENV_FILE)

logger = logging.getLogger("energy_watch.telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_LENGTH = 4096
# Telegram MarkdownV2 потребує екранування спецсимволів
MARKDOWN_V2_SPECIAL = r'_*[]()~`>#+-=|{}.!'


def _get_credentials() -> tuple[str, str]:
    """Отримати токен бота та chat_id з .env."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    return token, chat_id


def is_configured() -> bool:
    """Перевірити чи налаштовано Telegram інтеграцію."""
    token, chat_id = _get_credentials()
    return bool(token and chat_id)


def _escape_markdown_v2(text: str) -> str:
    """Екранувати спецсимволи для MarkdownV2."""
    for char in MARKDOWN_V2_SPECIAL:
        text = text.replace(char, f"\\{char}")
    return text


def _split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Розбити довге повідомлення на частини по межах абзаців/секцій.

    Намагається різати по '---' або подвійному переносу рядка,
    щоб не розривати логічні блоки.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Шукаємо найкраще місце для розрізу
        cut_at = max_length

        # Пріоритет 1: розріз по "---" (розділювач секцій)
        separator_pos = remaining.rfind("\n---\n", 0, max_length)
        if separator_pos > max_length // 3:
            cut_at = separator_pos + 1  # включити \n перед ---

        # Пріоритет 2: подвійний перенос рядка
        elif (double_newline := remaining.rfind("\n\n", 0, max_length)) > max_length // 3:
            cut_at = double_newline + 1

        # Пріоритет 3: одинарний перенос
        elif (single_newline := remaining.rfind("\n", 0, max_length)) > max_length // 3:
            cut_at = single_newline + 1

        chunks.append(remaining[:cut_at])
        remaining = remaining[cut_at:].lstrip("\n")

    return chunks


def _md_to_html(text: str) -> str:
    """Конвертувати Markdown у спрощений HTML для Telegram.

    Telegram підтримує обмежений HTML: <b>, <i>, <code>, <pre>, <a>.
    """
    # Заголовки -> жирний текст
    text = re.sub(r'^### (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'\n<b>📌 \1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'\n<b>📋 \1</b>', text, flags=re.MULTILINE)

    # **жирний** -> <b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # *курсив* -> <i>
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)

    # `код` -> <code>
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)

    # [текст](url) -> <a href="url">текст</a>
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)

    # Розділювачі
    text = text.replace("---", "─" * 30)

    return text


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Відправити повідомлення в Telegram.

    Автоматично розбиває на частини якщо текст > 4096 символів.
    Повертає True якщо всі частини відправлені успішно.
    """
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        logger.error(
            "Telegram not configured. Set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in .env"
        )
        return False

    # Конвертувати Markdown у HTML для кращого відображення
    if parse_mode == "HTML":
        text = _md_to_html(text)

    chunks = _split_message(text)
    total = len(chunks)
    success = True

    for i, chunk in enumerate(chunks, 1):
        if total > 1:
            header = f"[{i}/{total}]\n"
            chunk = header + chunk

        url = TELEGRAM_API.format(token=token, method="sendMessage")
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=15)
                data = resp.json()

                if data.get("ok"):
                    logger.debug("Sent chunk %d/%d", i, total)
                    break

                error_desc = data.get("description", "unknown error")
                logger.warning(
                    "Telegram API error (chunk %d/%d, attempt %d): %s",
                    i, total, attempt + 1, error_desc,
                )

                # Якщо помилка парсингу — спробувати без форматування
                if "parse" in error_desc.lower() and parse_mode == "HTML":
                    payload["parse_mode"] = ""
                    payload["text"] = chunk  # без HTML
                    continue

                if attempt < 2:
                    time.sleep(2 * (attempt + 1))

            except requests.RequestException as e:
                logger.warning(
                    "Telegram request failed (chunk %d/%d, attempt %d): %s",
                    i, total, attempt + 1, e,
                )
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
        else:
            logger.error("Failed to send chunk %d/%d after 3 attempts", i, total)
            success = False

        # Пауза між повідомленнями (Telegram rate limit: ~30 msg/sec)
        if i < total:
            time.sleep(1)

    return success


def send_report(report: str, run_date: str) -> bool:
    """Відправити щоденний звіт у Telegram.

    Додає заголовок з датою та розбиває на логічні секції.
    """
    if not is_configured():
        logger.info("Telegram not configured — skipping send")
        return False

    header = f"📋 <b>Energy Law Watch — {run_date}</b>\n{'─' * 30}\n\n"

    logger.info("Sending report for %s to Telegram...", run_date)
    result = send_message(header + report)

    if result:
        logger.info("Report sent to Telegram successfully")
    else:
        logger.error("Failed to send report to Telegram")

    return result


def send_notification(text: str) -> bool:
    """Відправити коротке сповіщення (без розбиття на частини)."""
    if not is_configured():
        return False
    return send_message(text)
