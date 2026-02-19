from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image
from openai import OpenAI

from .config import Settings


class VisionExtractor:
    def __init__(self, settings: Settings) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_vision_model

    @staticmethod
    def _render_pdf_page_jpeg_b64(pdf_path: Path, page_index: int) -> str:
        with fitz.open(str(pdf_path)) as doc:
            if page_index < 0 or page_index >= len(doc):
                return ""
            page = doc[page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            if max(img.size) > 1800:
                img.thumbnail((1800, 1800))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    @staticmethod
    def _image_file_to_jpeg_b64(image_path: Path) -> str:
        img = Image.open(image_path).convert("RGB")
        if max(img.size) > 1800:
            img.thumbnail((1800, 1800))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _describe_image_b64(self, b64: str) -> str:
        if not b64:
            return ""
        prompt = (
            "Analyze this study page/image. Extract key ideas, definitions, formulas, "
            "table/chart findings, and diagram relationships. Keep it concise and factual."
        )
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You extract learning-relevant visual details from study material.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
        )
        return (completion.choices[0].message.content or "").strip()

    def describe_pdf_page(self, pdf_path: Path, page_index: int) -> str:
        b64 = self._render_pdf_page_jpeg_b64(pdf_path, page_index)
        return self._describe_image_b64(b64)

    def describe_image_file(self, image_path: Path) -> str:
        b64 = self._image_file_to_jpeg_b64(image_path)
        return self._describe_image_b64(b64)
