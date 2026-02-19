from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

import yaml
from dotenv import dotenv_values


@dataclass
class LessonPrefs:
    target_words: int
    min_words: int
    max_words: int


@dataclass
class AnkiPrefs:
    cards_per_day: int
    min_cards: int
    max_cards: int
    failed_card_lookback_days: int
    failed_card_limit: int


@dataclass
class IngestionPrefs:
    default_pdf_pages_per_day: int
    default_links_per_day: int
    chunk_words: int
    max_total_units_per_day: int


@dataclass
class OpenAIPrefs:
    temperature: float
    max_source_chars: int
    enable_pdf_vision: bool
    enable_image_vision: bool
    vision_max_pages_per_day: int
    vision_max_images_per_day: int


@dataclass
class Settings:
    timezone: str
    schedule_hour: int
    schedule_minute: int
    content_dir: Path
    state_file: Path
    output_dir: Path
    lesson: LessonPrefs
    anki: AnkiPrefs
    ingestion: IngestionPrefs
    openai: OpenAIPrefs

    openai_api_key: str
    openai_model: str
    openai_vision_model: str

    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    smtp_to: str

    ankiconnect_url: str


def load_settings(config_path: str = "config.yaml") -> Settings:
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    config_file = Path(config_path)
    if not config_file.exists():
        config_file = project_root / config_path
    raw_env = dotenv_values(env_path) if env_path.exists() else {}
    env = {str(k).lstrip("\ufeff"): (v or "") for k, v in raw_env.items()}

    def get_env(name: str, default: str = "") -> str:
        # Process environment overrides .env file.
        v = os.getenv(name)
        if v is not None and v != "":
            return v.strip()

        value = str(env.get(name, default))

        # Remove BOM and invisible whitespace/newlines
        value = value.replace("\ufeff", "").strip()

        return value

    with open(config_file, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)


    return Settings(
        timezone=cfg["timezone"],
        schedule_hour=int(cfg["schedule_hour"]),
        schedule_minute=int(cfg["schedule_minute"]),
        content_dir=Path(cfg["content_dir"]),
        state_file=Path(cfg["state_file"]),
        output_dir=Path(cfg["output_dir"]),
        lesson=LessonPrefs(**cfg["lesson"]),
        anki=AnkiPrefs(**cfg["anki"]),
        ingestion=IngestionPrefs(**cfg["ingestion"]),
        openai=OpenAIPrefs(**cfg["openai"]),
        openai_api_key=get_env("OPENAI_API_KEY", ""),
        openai_model=get_env("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_vision_model=get_env(
            "OPENAI_VISION_MODEL", get_env("OPENAI_MODEL", "gpt-4.1-mini")
        ),
        smtp_host=get_env("SMTP_HOST", ""),
        smtp_port=int(get_env("SMTP_PORT", "587")),
        smtp_username=get_env("SMTP_USERNAME", ""),
        smtp_password=get_env("SMTP_PASSWORD", ""),
        smtp_from=get_env("SMTP_FROM", ""),
        smtp_to=get_env("SMTP_TO", ""),
        ankiconnect_url=get_env("ANKICONNECT_URL", "http://127.0.0.1:8765"),
    )
