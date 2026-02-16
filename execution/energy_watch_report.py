"""
Генерація звітів: Digest (A), Article Opportunities (B), Content Skeleton (C).

Секції A формуються детерміністично (шаблони).
Секції B і C використовують Anthropic API для AI-аналізу.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from energy_watch_config import (
    ANTHROPIC_MAX_TOKENS,
    ANTHROPIC_MODEL,
    DIGESTS_DIR,
    ENV_FILE,
)

logger = logging.getLogger("energy_watch.report")

# Завантажити .env
load_dotenv(ENV_FILE)


def _format_date(dt) -> str:
    """Форматувати дату для звіту."""
    if dt is None:
        return "дата невідома"
    if hasattr(dt, "strftime"):
        return dt.strftime("%d.%m.%Y %H:%M")
    return str(dt)


def _truncate_text(text: str, max_chars: int = 5000) -> str:
    """Обрізати текст якщо занадто довгий, зберігаючи початок і кінець."""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n\n[... текст скорочено ...]\n\n" + text[-half:]


# --- Секція A: Digest ---

def generate_digest_section(items: list[dict], run_date: str) -> str:
    """Згенерувати Секцію A — Сьогоднішній огляд (детерміністична частина).

    AI-аналіз (висновки, бізнес-вплив, чеклист) буде додано окремо.
    """
    lines = [
        f"# Щоденний огляд енергетичного законодавства",
        f"",
        f"**Дата:** {run_date}",
        f"**Час запуску:** 08:30",
        f"**Знайдено релевантних публікацій:** {len(items)}",
        f"",
        f"---",
        f"",
    ]

    if not items:
        lines.append("За останні 72 години нових релевантних публікацій не знайдено.")
        return "\n".join(lines)

    for i, item in enumerate(items, 1):
        pub_date = _format_date(item.get("published_date"))
        keywords = ", ".join(
            item.get("relevance_primary", [])[:5]
            + item.get("relevance_secondary", [])[:3]
        )

        lines.extend([
            f"## {i}. {item['title']}",
            f"",
            f"- **Джерело:** {item.get('source_short', item.get('source_id', ''))}",
            f"- **Дата публікації:** {pub_date}",
            f"- **Посилання:** {item.get('url', '')}",
            f"- **Тип:** {item.get('type', 'новина')}",
            f"- **Ключові слова:** {keywords}",
            f"",
        ])

        # Повний текст або стенограма
        full_text = item.get("full_text", "")
        if full_text:
            lines.extend([
                f"### Стенограма / повний текст",
                f"",
                _truncate_text(full_text),
                f"",
            ])
        else:
            lines.extend([
                f"### Текст",
                f"",
                f"**[Повний текст не вдалось завантажити]**",
                f"",
            ])

        # Плейсхолдери для AI-аналізу (заповнюються нижче)
        lines.extend([
            f"### Головний висновок",
            f"",
            f"{{ВИСНОВОК_{i}}}",
            f"",
            f"### Чому це важливо для бізнесу",
            f"",
            f"{{БІЗНЕС_{i}}}",
            f"",
            f"### Що перевірити юристу",
            f"",
            f"{{ЧЕКЛИСТ_{i}}}",
            f"",
            f"---",
            f"",
        ])

    return "\n".join(lines)


# --- AI-аналіз ---

def _call_anthropic(prompt: str, system: str = "") -> str:
    """Виклик Anthropic API для генерації тексту."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI analysis")
        return "[AI-аналіз недоступний: ANTHROPIC_API_KEY не налаштовано у .env]"

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            system=system or (
                "Ти — досвідчений український юрист-аналітик у сфері енергетичного права. "
                "Відповідай українською мовою. Будь конкретним і практичним. "
                "Зосередься на реальному впливі на бізнес."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except Exception as e:
        logger.error("Anthropic API call failed: %s", e)
        return f"[AI-аналіз недоступний: {e}]"


def enrich_digest_with_ai(digest_text: str, items: list[dict]) -> str:
    """Замінити плейсхолдери в дайджесті на AI-генерований аналіз."""
    for i, item in enumerate(items, 1):
        title = item.get("title", "")
        text_excerpt = _truncate_text(item.get("full_text", ""), 3000)
        source = item.get("source_short", "")
        pub_type = item.get("type", "новина")

        prompt = f"""Проаналізуй цю публікацію з офіційного джерела ({source}):

**Назва:** {title}
**Тип:** {pub_type}
**Текст (фрагмент):**
{text_excerpt}

Дай три блоки відповіді, ТОЧНО у такому форматі:

ВИСНОВОК:
(1–3 речення: що реально змінилось/оголошено і для кого)

БІЗНЕС:
- (3–6 булетів: вплив, ризики, можливості для енергетичних компаній, девелоперів, виробників)

ЧЕКЛИСТ:
- (3–7 пунктів: які документи/процеси/контракти/комплаєнс перевірити юристу)"""

        analysis = _call_anthropic(prompt)

        # Парсити відповідь на три блоки
        conclusion = ""
        business = ""
        checklist = ""

        parts = analysis.split("БІЗНЕС:")
        if len(parts) >= 2:
            conclusion_part = parts[0].replace("ВИСНОВОК:", "").strip()
            rest = parts[1]

            checklist_parts = rest.split("ЧЕКЛИСТ:")
            if len(checklist_parts) >= 2:
                business = checklist_parts[0].strip()
                checklist = checklist_parts[1].strip()
            else:
                business = rest.strip()

            conclusion = conclusion_part
        else:
            # Якщо формат не розпізнано — вставити як є
            conclusion = analysis

        digest_text = digest_text.replace(f"{{ВИСНОВОК_{i}}}", conclusion or "[Аналіз не згенеровано]")
        digest_text = digest_text.replace(f"{{БІЗНЕС_{i}}}", business or "[Аналіз не згенеровано]")
        digest_text = digest_text.replace(f"{{ЧЕКЛИСТ_{i}}}", checklist or "[Аналіз не згенеровано]")

    return digest_text


# --- Секція B: Article Opportunities ---

def generate_article_opportunities(items: list[dict]) -> str:
    """Згенерувати Секцію B — теми для статей юриста."""
    if not items:
        return (
            "## B) Теми для статей юриста\n\n"
            "Нових матеріалів не знайдено — рекомендації відсутні.\n"
        )

    summaries = []
    for i, item in enumerate(items[:10], 1):
        summaries.append(
            f"{i}. [{item.get('source_short', '')}] {item.get('title', '')} "
            f"(тип: {item.get('type', '')}, дата: {_format_date(item.get('published_date'))})"
        )

    prompt = f"""На основі цих сьогоднішніх публікацій з офіційних джерел:

{chr(10).join(summaries)}

Запропонуй 5–10 тем для юридичних статей для бізнес-аудиторії.

Для КОЖНОЇ теми вкажи:
1. **Заголовок** (привабливий, конкретний)
2. **Angle** (2–3 речення — під яким кутом писати)
3. **ЦА бізнесу** — хто виграє/постраждає
4. **Який біль вирішує стаття** — конкретна проблема
5. **Практичні поради** — що дати читачу

Формат — Markdown список. Мова — українська."""

    analysis = _call_anthropic(prompt)

    return f"## B) Теми для статей юриста (Article Opportunities)\n\n{analysis}\n"


# --- Секція C: Content Skeleton ---

def generate_content_skeleton(items: list[dict]) -> str:
    """Згенерувати Секцію C — скелет контенту для 1–3 найважливіших матеріалів."""
    if not items:
        return (
            "## C) Скелет контенту (Content Skeleton)\n\n"
            "Нових необроблених матеріалів не знайдено.\n"
        )

    # Обрати 1–3 найважливіші (за relevance_score)
    top_items = sorted(items, key=lambda x: x.get("relevance_score", 0), reverse=True)[:3]

    sections = ["## C) Скелет контенту (Content Skeleton)\n"]

    for idx, item in enumerate(top_items, 1):
        title = item.get("title", "")
        text_excerpt = _truncate_text(item.get("full_text", ""), 4000)
        source = item.get("source_short", "")

        prompt = f"""На основі цієї публікації ({source}):

**Назва:** {title}
**Текст:**
{text_excerpt}

Створи:

1) **Ключові тези** — 8–15 булетів, що передають суть

2) **План статті** з такою структурою:
   - Hook/лід (2–3 речення)
   - Контекст і що змінилось
   - Кому стосується
   - Вимоги/строки/процедури (якщо є)
   - Ризики та відповідальність
   - Практичні дії для бізнесу (чеклист)
   - FAQ (5–8 питань з відповідями)
   - Висновок (1 абзац)

3) **Міні-резюме для клієнта** — до 600 знаків, стисло і зрозуміло

Мова — українська. Формат — Markdown."""

        analysis = _call_anthropic(prompt)
        sections.append(f"### Матеріал {idx}: {title}\n\n{analysis}\n\n---\n")

    return "\n".join(sections)


# --- Збірка повного звіту ---

def compile_full_report(
    items: list[dict],
    run_date: str,
    use_ai: bool = True,
) -> str:
    """Скласти повний звіт з усіх трьох секцій."""
    # Секція A: Digest
    digest = generate_digest_section(items, run_date)
    if use_ai and items:
        digest = enrich_digest_with_ai(digest, items)

    # Секція B: Article Opportunities
    articles = generate_article_opportunities(items) if use_ai else (
        "## B) Теми для статей юриста\n\n[AI-аналіз вимкнено]\n"
    )

    # Секція C: Content Skeleton
    skeleton = generate_content_skeleton(items) if use_ai else (
        "## C) Скелет контенту\n\n[AI-аналіз вимкнено]\n"
    )

    report = f"{digest}\n\n{articles}\n\n{skeleton}"
    return report


def save_report(report: str, run_date: str) -> Path:
    """Зберегти звіт у файл."""
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGESTS_DIR / f"{run_date}.md"
    path.write_text(report, encoding="utf-8")
    logger.info("Report saved to %s", path)
    return path
