from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json

from .models import AppState, LinkState, SourceMeta


def load_state(path: Path) -> AppState:
    if not path.exists():
        return AppState()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sources = {sid: SourceMeta(**meta) for sid, meta in data.get("sources", {}).items()}
    link_state = LinkState(**data.get("link_state", {}))
    history = data.get("history", [])
    return AppState(sources=sources, link_state=link_state, history=history)


def save_state(path: Path, state: AppState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sources": {sid: asdict(meta) for sid, meta in state.sources.items()},
        "link_state": asdict(state.link_state),
        "history": state.history,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
