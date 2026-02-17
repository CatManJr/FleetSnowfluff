"""Chat history load/append/rewrite (JSONL)."""
from __future__ import annotations

import json
from pathlib import Path


def load_history(path: Path) -> list[dict[str, str]]:
    """Load records from JSONL file. Returns list of {timestamp, user, assistant}."""
    records: list[dict[str, str]] = []
    if not path.exists():
        return records
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        user_text = str(item.get("user", "")).strip()
        assistant_text = str(item.get("assistant", "")).strip()
        ts = str(item.get("timestamp", "")).strip()
        if user_text and assistant_text:
            records.append(
                {"timestamp": ts, "user": user_text, "assistant": assistant_text}
            )
    return records


def append_history_line(path: Path, payload: dict, config_dir: Path) -> None:
    """Append one JSON line to history file. Creates config_dir if needed."""
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass


def rewrite_history(path: Path, records: list[dict], config_dir: Path) -> None:
    """Overwrite history file with all records. Creates config_dir if needed."""
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for item in records:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    except OSError:
        raise  # Caller may show "保存失败" etc.
