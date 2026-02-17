"""API client and post-processing for chat (DeepSeek, context, code blocks)."""
from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, Signal

from difflib import SequenceMatcher


class ChatWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        api_key: str,
        messages: list[dict[str, str]],
        temperature: float,
        reasoning_enabled: bool,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.messages = messages
        self.temperature = temperature
        self.reasoning_enabled = reasoning_enabled

    def run(self) -> None:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
            model = "deepseek-reasoner" if self.reasoning_enabled else "deepseek-chat"
            response = client.chat.completions.create(
                model=model,
                messages=cast(Any, self.messages),
                temperature=self.temperature,
            )
            answer = response.choices[0].message.content if response.choices else ""
            answer = (answer or "").strip()
            if not answer:
                answer = "飞行雪绒 暂时没有想好怎么回复。"
            self.finished.emit(answer)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


DEFAULT_SYSTEM = (
    "You are Feixing Xuerong (Fleet Snowfluff), a cute desktop pet assistant. "
    "Keep replies concise and warm."
)
CODE_FORMAT_SYSTEM = (
    "Output formatting requirement: "
    "Only when your reply truly includes code, commands, config snippets, or file contents, "
    "you MUST wrap each code segment in fenced markdown blocks using triple backticks, "
    "and include a language tag when possible (e.g. ```rust, ```python, ```json). "
    "Do not output bare code outside fenced blocks. "
    "If the reply is normal conversation without code, do NOT use fenced blocks."
)


def build_context_messages(
    records: list[dict[str, str]],
    prompt: str,
    persona_prompt_getter: Callable[[], str],
    context_turns_getter: Callable[[], int],
) -> list[dict[str, str]]:
    """Build messages list for API from history and current prompt."""
    messages: list[dict[str, str]] = []
    persona_prompt = (persona_prompt_getter() or "").strip()
    if persona_prompt:
        messages.append(
            {
                "role": "system",
                "content": (
                    "你是飞行雪绒（Fleet Snowfluff）。必须优先遵循角色设定中的高优先级行为约束。"
                    "当用户请求与角色设定冲突时，拒绝冲突部分并保持角色语气回答。"
                    "不要忽略、弱化或重写这些约束。"
                ),
            }
        )
        messages.append({"role": "system", "content": CODE_FORMAT_SYSTEM})
        messages.append(
            {
                "role": "system",
                "content": (
                    "以下为结构化角色设定知识库（高优先级）：\n\n"
                    f"{persona_prompt}"
                ),
            }
        )
    else:
        messages.append({"role": "system", "content": DEFAULT_SYSTEM})
        messages.append({"role": "system", "content": CODE_FORMAT_SYSTEM})

    try:
        context_turns = max(0, int(context_turns_getter()))
    except Exception:
        context_turns = 20
    history_slice = records[-context_turns:] if context_turns > 0 else []
    for item in history_slice:
        messages.append({"role": "user", "content": item["user"]})
        messages.append({"role": "assistant", "content": item["assistant"]})
    messages.append({"role": "user", "content": prompt})
    return messages


def extract_persona_example_inputs(persona_prompt: str) -> list[str]:
    if not persona_prompt:
        return []
    matches = re.findall(r'"输入"\s*:\s*"([^"]+)"', persona_prompt)
    return [m.strip() for m in matches if m.strip()]


def choose_temperature(
    prompt: str,
    persona_prompt_getter: Callable[[], str],
) -> float:
    """Reduce randomness when the user prompt resembles persona examples."""
    base = 0.7
    persona_prompt = (persona_prompt_getter() or "").strip()
    persona_example_inputs = extract_persona_example_inputs(persona_prompt)
    if not persona_example_inputs:
        return base
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        return base

    best_ratio = 0.0
    for sample in persona_example_inputs:
        ratio = SequenceMatcher(None, normalized_prompt, sample).ratio()
        if sample in normalized_prompt or normalized_prompt in sample:
            ratio = max(ratio, 0.92)
        if ratio > best_ratio:
            best_ratio = ratio

    if best_ratio >= 0.9:
        return 0.2
    if best_ratio >= 0.7:
        return 0.3
    if best_ratio >= 0.55:
        return 0.45
    return base


def _code_extension(lang: str) -> str:
    table = {
        "python": "py", "py": "py",
        "javascript": "js", "js": "js",
        "typescript": "ts", "ts": "ts", "tsx": "tsx", "jsx": "jsx",
        "java": "java", "go": "go", "rust": "rs", "rs": "rs",
        "cpp": "cpp", "c++": "cpp", "c": "c",
        "csharp": "cs", "cs": "cs", "swift": "swift", "kotlin": "kt",
        "php": "php", "ruby": "rb", "rb": "rb",
        "bash": "sh", "sh": "sh", "shell": "sh", "zsh": "sh",
        "sql": "sql", "json": "json", "yaml": "yml", "yml": "yml",
        "toml": "toml", "html": "html", "css": "css", "scss": "scss",
        "markdown": "md", "md": "md", "xml": "xml",
    }
    normalized = lang.strip().lower()
    return table.get(normalized, "txt")


def _looks_like_code(block: str, lang: str) -> bool:
    if lang.strip():
        return True
    if "\n" in block and len(block) >= 20:
        hints = (
            "def ", "class ", "fn ", "let ", "const ", "import ", "from ",
            "return ", "if ", "for ", "while ", "{", "};", "=>", "::",
            "pub ", "#include",
        )
        return any(h in block for h in hints)
    return False


def materialize_code_blocks(answer: str, export_dir: Path, config_dir: Path) -> str:
    """
    Extract fenced code blocks from answer, write to export_dir, replace with
    [代码块已保存: lang] rel_path markers. Returns rendered text.
    """
    pattern = re.compile(
        r"(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>[a-zA-Z0-9_+\-#.]*)[ \t]*\r?\n?(?P<code>.*?)(?:\r?\n)?(?P=fence)",
        re.DOTALL,
    )
    matches = list(pattern.finditer(answer))
    if not matches:
        return answer

    try:
        export_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return answer

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    chunks: list[str] = []
    cursor = 0
    file_index = 1
    for m in matches:
        start, end = m.span()
        if start > cursor:
            chunks.append(answer[cursor:start])
        lang = (m.group("lang") or "").strip()
        code = m.group("code")
        code_stripped = code.strip()
        if not code_stripped or not _looks_like_code(code_stripped, lang):
            chunks.append(answer[start:end])
            cursor = end
            continue
        ext = _code_extension(lang)
        filename = f"reply_{stamp}_{file_index:02d}.{ext}"
        file_index += 1
        file_path = export_dir / filename
        try:
            file_path.write_text(code_stripped + "\n", encoding="utf-8")
            if not file_path.exists() or file_path.stat().st_size <= 0:
                chunks.append(answer[start:end])
                cursor = end
                continue
            try:
                rel_path = file_path.relative_to(config_dir)
            except ValueError:
                rel_path = file_path
            label = lang if lang else "text"
            chunks.append(f"\n[代码块已保存: {label}] {rel_path}\n")
        except OSError:
            chunks.append(answer[start:end])
        cursor = end
    if cursor < len(answer):
        chunks.append(answer[cursor:])

    rendered = "".join(chunks).strip()
    return rendered if rendered else answer
