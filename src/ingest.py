from __future__ import annotations

from pathlib import Path
import hashlib
import re

import requests
from bs4 import BeautifulSoup
from docx import Document
from PIL import Image
import pytesseract
from pypdf import PdfReader

from .config import IngestionPrefs
from .models import SourceUnit


def file_fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(8192)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def split_words(text: str, chunk_words: int) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_words):
        chunks.append(" ".join(words[i : i + chunk_words]))
    return [c for c in chunks if c.strip()]


def read_pdf_units(path: Path) -> list[SourceUnit]:
    reader = PdfReader(str(path))
    units = []
    for i, page in enumerate(reader.pages):
        units.append(SourceUnit(unit_index=i, text=page.extract_text() or ""))
    return units


def read_docx_units(path: Path, chunk_words: int) -> list[SourceUnit]:
    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs)
    return [
        SourceUnit(unit_index=i, text=t)
        for i, t in enumerate(split_words(text, chunk_words))
    ]


def read_text_units(path: Path, chunk_words: int) -> list[SourceUnit]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [
        SourceUnit(unit_index=i, text=t)
        for i, t in enumerate(split_words(text, chunk_words))
    ]


def read_image_units(path: Path) -> list[SourceUnit]:
    text = pytesseract.image_to_string(Image.open(path))
    return [SourceUnit(unit_index=0, text=text)]


def fetch_url_text(url: str, timeout: int = 15) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "lesson-bot/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.extract()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return text[:12000]


def discover_files(content_dir: Path) -> list[Path]:
    exts = {".pdf", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
    files = []
    for p in content_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts and p.name.lower() != "links.txt":
            files.append(p)
    return sorted(files)


def load_links(content_dir: Path) -> list[str]:
    links_file = content_dir / "links.txt"
    if not links_file.exists():
        return []
    urls = []
    for line in links_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def read_units_for_file(path: Path, prefs: IngestionPrefs) -> list[SourceUnit]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return read_pdf_units(path)
    if ext == ".docx":
        return read_docx_units(path, prefs.chunk_words)
    if ext in {".txt", ".md"}:
        return read_text_units(path, prefs.chunk_words)
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return read_image_units(path)
    return []
