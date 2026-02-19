from __future__ import annotations

from datetime import datetime
from pathlib import Path
import random

import genanki

from .models import LessonBundle


def save_lesson(output_dir: Path, lesson_md: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    out = output_dir / f"lesson-{stamp}.md"
    out.write_text(lesson_md, encoding="utf-8")
    return out


def build_anki_deck(output_dir: Path, bundle: LessonBundle) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")

    model_id = random.randint(10**9, 2 * 10**9 - 1)
    deck_id = random.randint(10**9, 2 * 10**9 - 1)

    model = genanki.Model(
        model_id,
        "DailyLessonModel",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[
            {
                "name": "Card 1",
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
            }
        ],
    )

    deck = genanki.Deck(deck_id, f"MentorLoop {stamp}")
    for card in bundle.cards:
        front = (card.get("front") or "").strip()
        back = (card.get("back") or "").strip()
        if front and back:
            deck.add_note(genanki.Note(model=model, fields=[front, back]))

    out = output_dir / f"deck-{stamp}.apkg"
    genanki.Package(deck).write_to_file(str(out))
    return out
