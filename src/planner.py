from __future__ import annotations

from .config import Settings
from .models import DailySelection


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def fallback_selection(
    settings: Settings,
    source_ids: list[str],
    pdf_like_source_ids: list[str],
    links_remaining: int,
) -> DailySelection:
    target_words = clamp(
        settings.lesson.target_words,
        settings.lesson.min_words,
        settings.lesson.max_words,
    )
    target_cards = clamp(
        settings.anki.cards_per_day,
        settings.anki.min_cards,
        settings.anki.max_cards,
    )

    per_source: dict[str, list[int]] = {}
    daily_units_budget = settings.ingestion.max_total_units_per_day

    if pdf_like_source_ids:
        per_pdf = max(
            1,
            settings.ingestion.default_pdf_pages_per_day
            // max(1, len(pdf_like_source_ids)),
        )
        used = 0
        for sid in pdf_like_source_ids:
            if used >= daily_units_budget:
                break
            count = min(per_pdf, daily_units_budget - used)
            per_source[sid] = list(range(count))
            used += count

    if not per_source and source_ids:
        per_source[source_ids[0]] = [0]

    links_to_use = min(
        settings.ingestion.default_links_per_day, max(0, links_remaining)
    )

    return DailySelection(
        source_units=per_source,
        links=[],
        target_lesson_words=target_words,
        target_cards=target_cards,
    )
