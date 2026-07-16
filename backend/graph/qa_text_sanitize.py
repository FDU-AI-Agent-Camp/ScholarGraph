"""Streaming and final sanitization for QA answer text.

Removes Markdown artifacts (backticks, bold, headers) from LLM output before
SSE ``message`` events. Citation markers ``[CITE:…]`` must already be stripped
by ``qa.py`` before text reaches this module.
"""

from __future__ import annotations

import re

_MULTI_SPACE_RE = re.compile(r" {2,}")
_STAR_RUN_RE = re.compile(r"\*{1,}")


def sanitize_qa_text_chunk(text: str) -> str:
    """Sanitize a complete text fragment with the streaming FSM."""
    if not text:
        return text
    sanitizer = QaTextSanitizer()
    return sanitizer.feed(text) + sanitizer.flush()


def sanitize_qa_answer_final(text: str) -> str:
    """Final pass over the assembled answer — fixes streaming boundary leaks."""
    if not text:
        return text
    result = sanitize_qa_text_chunk(text)
    result = result.replace("`", "")
    result = _STAR_RUN_RE.sub("", result)
    result = _MULTI_SPACE_RE.sub(" ", result)
    return result


class QaTextSanitizer:
    """FSM-based sanitizer for streaming QA ``message.delta`` payloads."""

    __slots__ = (
        "_at_line_start",
        "_held_text",
        "_in_backtick_span",
        "_in_bold_span",
        "_pending_star",
    )

    def __init__(self) -> None:
        self._held_text = ""
        self._in_backtick_span = False
        self._in_bold_span = False
        self._pending_star = False
        self._at_line_start = True

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        released: list[str] = []
        index = 0
        length = len(delta)

        if self._pending_star:
            index = self._consume_pending_star(delta, released)
            length = len(delta)

        while index < length:
            char = delta[index]

            if self._in_backtick_span:
                if char == "`":
                    released.append(self._held_text)
                    if self._held_text:
                        self._at_line_start = self._held_text.endswith(("\n", "\r"))
                    self._held_text = ""
                    self._in_backtick_span = False
                else:
                    self._held_text += char
                index += 1
                continue

            if self._in_bold_span:
                if char == "*":
                    if index + 1 >= length:
                        self._pending_star = True
                        break
                    if delta[index + 1] == "*":
                        released.append(self._held_text)
                        if self._held_text:
                            self._at_line_start = self._held_text.endswith(("\n", "\r"))
                        self._held_text = ""
                        self._in_bold_span = False
                        index += 2
                        continue
                self._held_text += char
                index += 1
                continue

            if char == "`":
                self._in_backtick_span = True
                index += 1
                continue

            if char == "*":
                if index + 1 >= length:
                    self._pending_star = True
                    break
                if delta[index + 1] == "*":
                    self._in_bold_span = True
                    index += 2
                    continue
                index += 1
                continue

            if char == "#" and self._at_line_start:
                while index < length and delta[index] in {"#", " "}:
                    index += 1
                self._at_line_start = False
                continue

            released.append(char)
            self._at_line_start = char in {"\n", "\r"}
            index += 1

        return "".join(released)

    def flush(self) -> str:
        remaining = self._held_text
        self._held_text = ""
        self._in_backtick_span = False
        self._in_bold_span = False
        self._pending_star = False
        if not remaining:
            return ""
        return _MULTI_SPACE_RE.sub(" ", remaining)

    def _consume_pending_star(self, delta: str, released: list[str]) -> int:
        self._pending_star = False
        if not delta:
            return 0
        if delta[0] != "*":
            return 0

        if self._in_bold_span:
            released.append(self._held_text)
            if self._held_text:
                self._at_line_start = self._held_text.endswith(("\n", "\r"))
            self._held_text = ""
            self._in_bold_span = False
        else:
            self._in_bold_span = True
        return 1
