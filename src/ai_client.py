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
        self.settings = settings

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

    def generate_lesson(
    self,
    target_words: int,
    source_packets: list[dict],
    failed_cards: list[dict],
    ) -> str:
        native = self.settings.language.student_native_language
        target = self.settings.language.target_language
        
        prompt = {
            "lesson_type": f"{target} language learning",
            "student_native_language": native,
            "target_language": target,

            "student_goal": f"Understand today's {target} material and correct recent mistakes",

            "lesson_source_text": source_packets,
            "recent_failures": failed_cards,

            "teaching_style": "Warm, engaging, mentor-style. Avoid textbook tone.",

            "rules": [
                f"All explanations must be in {native}.",
                f"Main examples must be in {target}.",
                f"Do not explain grammar fully in {target}.",
                f"Assume the student is a native {native} speaker."
            ],

            "constraints": {
                "target_words": target_words,
            },
        }

        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": f"""
                                    You are a professional {target} language tutor.

                                    The student is a native {native} speaker learning {target}.

                                    Teaching rules:
                                    - All explanations must be written in {native}.
                                    - All main examples must be written in {target}.
                                    - Provide translations into {native} when helpful.
                                    - Never switch fully into {target} for explanations.
                                    """
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt),
                },
            ],
            temperature=0.5,  # <-- more human
        )

        return response.output[0].content[0].text.strip()
    
    def generate_cards(
    self,
    lesson_markdown: str,
    failed_cards: list[dict],
    target_cards: int,
    ) -> list[dict]:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
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
            "required": ["cards"],
        }
        native = self.settings.language.student_native_language
        target = self.settings.language.target_language

        payload = {
            "lesson": lesson_markdown,
            "recent_failures": failed_cards,
            "target_cards": target_cards,
            "card_design_rules": [
                "Create a balanced mix of card directions.",
                f"Some cards must show {target} on the front and require {native} on the back.",
                f"Some cards must show {native} on the front and require {target} on the back.",
                "Some cards may test grammar or sentence construction.",
                "Front must contain only the prompt.",
                "Back must contain only the correct answer."
            ]       
        }

        data = self._json_response(
            system_prompt=f"""You are designing high-quality Anki cards for a {target} learner whose native language is {native}.
                             Create varied card directions ({target}→{native} and {native}→{target}).
                             Return valid JSON only.""",
            user_payload=payload,
            schema_name="cards",
            schema=schema,
            temperature=0,
        )

        return data["cards"][:target_cards]
