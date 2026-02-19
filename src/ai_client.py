from __future__ import annotations

import json
from openai import OpenAI

from .config import Settings
from .models import LessonBundle


class AIClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is missing")
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    @staticmethod
    def _lesson_obj_to_markdown(obj: dict) -> str:
        title = str(obj.get("title") or "MentorLoop").strip()
        sections = obj.get("sections") or []
        lines = [f"# {title}", ""]
        if isinstance(sections, list) and sections:
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                st = str(sec.get("title") or "Section").strip()
                body = str(sec.get("content") or "").strip()
                lines.append(f"## {st}")
                lines.append("")
                lines.append(body)
                lines.append("")
        else:
            body = str(obj.get("content") or "").strip()
            if body:
                lines.append(body)
        return "\n".join(lines).strip()

    @staticmethod
    def _normalize_lesson_payload(data: dict) -> dict:
        if not isinstance(data, dict):
            return {"lesson_markdown": "", "cards": []}

        # Handle wrapped payloads from some models/SDK paths.
        if "result" in data and isinstance(data["result"], dict):
            data = data["result"]
        if "data" in data and isinstance(data["data"], dict):
            data = data["data"]

        lesson = (
            data.get("lesson_markdown")
            or data.get("lesson")
            or data.get("content")
            or data.get("summary")
            or ""
        )
        if not lesson and ("title" in data or "sections" in data):
            lesson = AIClient._lesson_obj_to_markdown(data)
        cards = data.get("cards") or data.get("anki_cards") or data.get("flashcards") or []

        # Accept cards encoded as {"cards": {"items":[...]}}
        if isinstance(cards, dict):
            cards = cards.get("items", [])
        if not isinstance(cards, list):
            cards = []

        normalized_cards = []
        for c in cards:
            if not isinstance(c, dict):
                continue
            front = c.get("front") or c.get("question") or c.get("q") or ""
            back = c.get("back") or c.get("answer") or c.get("a") or ""
            if front and back:
                normalized_cards.append({"front": str(front), "back": str(back)})

        if isinstance(lesson, dict):
            lesson = AIClient._lesson_obj_to_markdown(lesson)
        elif isinstance(lesson, list):
            lesson = "\n".join(str(x) for x in lesson)
        elif isinstance(lesson, str):
            maybe = lesson.strip()
            if maybe.startswith("{") and maybe.endswith("}"):
                try:
                    parsed = json.loads(maybe)
                    if isinstance(parsed, dict) and ("title" in parsed or "sections" in parsed):
                        lesson = AIClient._lesson_obj_to_markdown(parsed)
                except Exception:
                    pass
        return {"lesson_markdown": str(lesson).strip(), "cards": normalized_cards}

    def _json_response(self, system_prompt: str, user_payload: dict, schema_name: str, schema: dict, temperature: float) -> dict:
        content = json.dumps(user_payload)
        def _is_temp_unsupported(err: Exception) -> bool:
            msg = str(err).lower()
            return "temperature" in msg and "unsupported" in msg

        if not hasattr(self.client, "responses"):
            raise RuntimeError(
                "Installed openai SDK is too old for strict schema mode. "
                "Run: pip install -U openai"
            )
        kwargs = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": temperature,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                },
            },
        }
        try:
            response = self.client.responses.create(**kwargs)
        except TypeError as e:
            if "text" not in str(e).lower() or "unexpected keyword argument" not in str(e).lower():
                raise
            kwargs.pop("text", None)
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema},
            }
            response = self.client.responses.create(**kwargs)
        except Exception as e:
            if not _is_temp_unsupported(e):
                raise
            kwargs.pop("temperature", None)
            response = self.client.responses.create(**kwargs)
        text = response.output[0].content[0].text

        return json.loads(text)


    def plan_selection(
        self,
        source_stats: list[dict],
        preferences: dict,
    ) -> dict:
        schema = {
            "type": "object",
            "properties": {
                "target_lesson_words": {"type": "integer"},
                "target_cards": {"type": "integer"},
                "per_source_units": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_id": {"type": "string"},
                            "units": {"type": "integer"},
                        },
                        "required": ["source_id", "units"],
                    },
                },
                "links_to_use": {"type": "integer"},
            },
            "required": ["target_lesson_words", "target_cards", "per_source_units", "links_to_use"],
        }

        prompt = {
            "source_stats": source_stats,
            "preferences": preferences,
        }

        return self._json_response(
            system_prompt="You are a study-load planner. Return valid JSON only.",
            user_payload=prompt,
            schema_name="plan",
            schema=schema,
            temperature=0,
        )

    def generate_lesson_and_cards(
        self,
        target_words: int,
        target_cards: int,
        source_packets: list[dict],
        failed_cards: list[dict],
    ) -> LessonBundle:
        schema = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "lesson_markdown": {"type": "string"},
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "front": {"type": "string"},
                    "back": {"type": "string"},
                },
                "required": ["front", "back"],
            },
        },
    },
    "required": ["lesson_markdown", "cards"],
}

        prompt = {
    "student_goal": "Understand today's textbook material and correct recent mistakes",
    "lesson_source_text": source_packets,
    "recent_failures": failed_cards,
    "teaching_instructions": [
        "Teach the main material from the textbook.",
        "Explicitly re-teach the failed vocabulary.",
        "Create example sentences using failed words in new contexts.",
        "Include comparisons if the mistake is likely confusion (e.g., weil vs denn).",
        "Make reinforcement feel like part of the lesson, not a separate drill."
    ],
    "constraints": {
        "target_words": target_words,
        "target_cards": target_cards
    }
}

        data = self._json_response(
            system_prompt="You are an instructional designer. Return valid JSON only.",
            user_payload=prompt,
            schema_name="lesson",
            schema=schema,
            temperature=0,
        )
        normalized = self._normalize_lesson_payload(data)
        if not normalized["lesson_markdown"]:
            raise ValueError(f"Model response missing lesson content. Raw keys: {list(data.keys())}")
        if not normalized["cards"]:
            raise ValueError(f"Model response missing Anki cards. Raw keys: {list(data.keys())}")
        cards = normalized["cards"][:target_cards]
        return LessonBundle(
            lesson_markdown=normalized["lesson_markdown"],
            cards=cards,
        )
