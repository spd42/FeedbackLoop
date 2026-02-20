from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse

from .ai_client import AIClient
from .anki_integration import AnkiConnectClient
from .config import load_settings
from .emailer import send_email
from .generator import build_anki_deck, save_lesson
from .ingest import (
    discover_files,
    fetch_url_text,
    file_fingerprint,
    load_links,
    read_units_for_file,
)
from .models import AppState, DailySelection, LessonBundle, SourceMeta
from .planner import fallback_selection
from .scheduler import run_daily
from .storage import load_state, save_state
from .vision import VisionExtractor


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _source_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in {".txt", ".md"}:
        return "text"
    return "image"


def sync_sources(settings, state: AppState):
    settings.content_dir.mkdir(parents=True, exist_ok=True)
    files = discover_files(settings.content_dir)

    seen = set()
    for fp in files:
        sid = str(fp.resolve())
        seen.add(sid)
        fingerprint = file_fingerprint(fp)
        if sid not in state.sources or state.sources[sid].fingerprint != fingerprint:
            units = read_units_for_file(fp, settings.ingestion)
            state.sources[sid] = SourceMeta(
                source_id=sid,
                path=str(fp),
                source_type=_source_type(fp),
                fingerprint=fingerprint,
                units=len(units),
                next_unit=0,
            )

    for sid in list(state.sources.keys()):
        if sid not in seen:
            del state.sources[sid]

    state.link_state.links = load_links(settings.content_dir)
    if state.link_state.next_index > len(state.link_state.links):
        state.link_state.next_index = len(state.link_state.links)


def choose_daily_selection(settings, state: AppState) -> DailySelection:
    source_ids = sorted(state.sources.keys())
    pdf_ids = [sid for sid in source_ids if state.sources[sid].source_type == "pdf"]
    links_remaining = len(state.link_state.links) - state.link_state.next_index
    sel = fallback_selection(settings, source_ids, pdf_ids, links_remaining)

    if settings.openai_api_key and source_ids:
        try:
            ai = AIClient(settings)
            stats = []
            for sid in source_ids:
                meta = state.sources[sid]
                remaining = max(0, meta.units - meta.next_unit)
                stats.append(
                    {
                        "source_id": sid,
                        "source_type": meta.source_type,
                        "remaining_units": remaining,
                    }
                )
            prefs = {
                "target_lesson_words": settings.lesson.target_words,
                "min_words": settings.lesson.min_words,
                "max_words": settings.lesson.max_words,
                "cards_per_day": settings.anki.cards_per_day,
                "min_cards": settings.anki.min_cards,
                "max_cards": settings.anki.max_cards,
                "default_links_per_day": settings.ingestion.default_links_per_day,
                "max_total_units_per_day": settings.ingestion.max_total_units_per_day,
            }
            plan = ai.plan_selection(source_stats=stats, preferences=prefs)
            sel.target_lesson_words = _clamp(
                int(plan.get("target_lesson_words", sel.target_lesson_words)),
                settings.lesson.min_words,
                settings.lesson.max_words,
            )
            sel.target_cards = _clamp(
                int(plan.get("target_cards", sel.target_cards)),
                settings.anki.min_cards,
                settings.anki.max_cards,
            )
            ai_map = {}
            units_used = 0
            for row in plan.get("per_source_units", []):
                sid = row.get("source_id")
                units = int(row.get("units", 0))
                if sid in state.sources and units > 0 and units_used < settings.ingestion.max_total_units_per_day:
                    allowed = min(units, settings.ingestion.max_total_units_per_day - units_used)
                    ai_map[sid] = list(range(allowed))
                    units_used += allowed
            if ai_map:
                sel.source_units = ai_map
            links_hint = int(plan.get("links_to_use", settings.ingestion.default_links_per_day))
            sel.links = state.link_state.links[
                state.link_state.next_index: state.link_state.next_index + max(0, links_hint)
            ]
        except Exception:
            pass

    # Translate relative unit placeholders to absolute ranges using next_unit cursors.
    mapped = {}
    for sid, unit_stub in sel.source_units.items():
        meta = state.sources.get(sid)
        if not meta or meta.next_unit >= meta.units:
            continue
        count = len(unit_stub)
        start = meta.next_unit
        end = min(meta.units, start + count)
        if end > start:
            mapped[sid] = list(range(start, end))
    sel.source_units = mapped

    if not sel.links:
        links_to_use = min(
            settings.ingestion.default_links_per_day,
            len(state.link_state.links) - state.link_state.next_index,
        )
        sel.links = state.link_state.links[state.link_state.next_index:state.link_state.next_index + links_to_use]
    return sel


def collect_packets(settings, state: AppState, sel: DailySelection) -> list[dict]:
    packets: list[dict] = []
    vision = None
    vision_pages_used = 0
    vision_images_used = 0
    if settings.openai_api_key and (settings.openai.enable_pdf_vision or settings.openai.enable_image_vision):
        try:
            vision = VisionExtractor(settings)
        except Exception:
            vision = None

    for sid, unit_indexes in sel.source_units.items():
        meta = state.sources[sid]
        units = read_units_for_file(Path(meta.path), settings.ingestion)
        for idx in unit_indexes:
            if 0 <= idx < len(units):
                text = units[idx].text
                if (
                    vision
                    and meta.source_type == "pdf"
                    and vision_pages_used < settings.openai.vision_max_pages_per_day
                ):
                    try:
                        visual = vision.describe_pdf_page(Path(meta.path), idx)
                    except Exception:
                        visual = ""
                    if visual:
                        text = (text or "").strip() + "\n\n[Visual Analysis]\n" + visual
                    vision_pages_used += 1
                elif (
                    vision
                    and meta.source_type == "image"
                    and settings.openai.enable_image_vision
                    and vision_images_used < settings.openai.vision_max_images_per_day
                ):
                    try:
                        visual = vision.describe_image_file(Path(meta.path))
                    except Exception:
                        visual = ""
                    if visual:
                        text = (text or "").strip() + "\n\n[Visual Analysis]\n" + visual
                    vision_images_used += 1
                packets.append(
                    {
                        "source": meta.path,
                        "unit_index": idx,
                        "text": text,
                    }
                )

    for link in sel.links:
        try:
            text = fetch_url_text(link)
        except Exception:
            text = ""
        packets.append({"source": link, "unit_index": 0, "text": text})

    max_chars = settings.openai.max_source_chars
    joined = []
    used = 0
    for p in packets:
        t = (p.get("text") or "").strip()
        if not t:
            continue
        budget = max_chars - used
        if budget <= 0:
            break
        t = t[:budget]
        used += len(t)
        joined.append({**p, "text": t})

    return joined


def get_failed_cards(settings):
    client = AnkiConnectClient(settings.ankiconnect_url)
    try:
        cards = client.recent_failed_cards(
            settings.anki.failed_card_lookback_days,
            settings.anki.failed_card_limit,
        )
        return [{"front": c.front, "back": c.back} for c in cards]
    except Exception:
        return []


def advance_state(state: AppState, sel: DailySelection) -> None:
    for sid, unit_indexes in sel.source_units.items():
        if not unit_indexes:
            continue
        meta = state.sources[sid]
        meta.next_unit = min(meta.units, max(unit_indexes) + 1)

    state.link_state.next_index += len(sel.links)
    state.history.append(
        {
            "ts": datetime.now().isoformat(),
            "sources_used": {k: len(v) for k, v in sel.source_units.items()},
            "links_used": len(sel.links),
            "target_words": sel.target_lesson_words,
            "target_cards": sel.target_cards,
        }
    )


def run_once() -> None:
    settings = load_settings()
    state = load_state(settings.state_file)

    sync_sources(settings, state)
    sel = choose_daily_selection(settings, state)
    packets = collect_packets(settings, state, sel)
    failed_cards = get_failed_cards(settings)

    if not packets:
        raise RuntimeError("No usable content found for today's lesson")

    ai = AIClient(settings)
    lesson_markdown = ai.generate_lesson(
    target_words=sel.target_lesson_words,
    source_packets=packets,
    failed_cards=failed_cards,
    )

    cards = ai.generate_cards(
        lesson_markdown=lesson_markdown,
        failed_cards=failed_cards,
        target_cards=sel.target_cards,
    )

    bundle = LessonBundle(
        lesson_markdown=lesson_markdown,
        cards=cards,
    )

    lesson_file = save_lesson(settings.output_dir, bundle.lesson_markdown)
    deck_file = build_anki_deck(settings.output_dir, bundle)

    send_email(
        settings,
        subject=f"MentorLoop - {datetime.now().strftime('%Y-%m-%d')}",
        body=bundle.lesson_markdown,
        attachments=[lesson_file, deck_file],
    )

    advance_state(state, sel)
    save_state(settings.state_file, state)


def serve() -> None:
    settings = load_settings()
    run_daily(settings.timezone, settings.schedule_hour, settings.schedule_minute, run_once)


def main() -> None:
    parser = argparse.ArgumentParser(description="MentorLoop")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run-once")
    sub.add_parser("serve")
    args = parser.parse_args()

    if args.cmd == "run-once":
        run_once()
    elif args.cmd == "serve":
        serve()


if __name__ == "__main__":
    main()
