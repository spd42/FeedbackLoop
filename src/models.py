from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceUnit:
    unit_index: int
    text: str


@dataclass
class SourceMeta:
    source_id: str
    path: str
    source_type: str
    fingerprint: str
    units: int
    next_unit: int = 0


@dataclass
class LinkState:
    links: list[str] = field(default_factory=list)
    next_index: int = 0


@dataclass
class AppState:
    sources: dict[str, SourceMeta] = field(default_factory=dict)
    link_state: LinkState = field(default_factory=LinkState)
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FailedCard:
    front: str
    back: str


@dataclass
class LessonBundle:
    lesson_markdown: str
    cards: list[dict[str, str]]


@dataclass
class DailySelection:
    source_units: dict[str, list[int]]
    links: list[str]
    target_lesson_words: int
    target_cards: int
