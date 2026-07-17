# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Cross-stack contract: backend extract_constants ⊂ frontend extractWarnings catalog."""

from __future__ import annotations

import re
from pathlib import Path

import backend.agents.extract_constants as extract_constants

REPO_ROOT = Path(__file__).resolve().parent.parent
FE_EXTRACT_WARNINGS = REPO_ROOT / "frontend" / "src" / "utils" / "extractWarnings.ts"


def _backend_code_message_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for name in dir(extract_constants):
        if not name.endswith("_CODE"):
            continue
        message_name = f"{name[: -len('_CODE')]}_MESSAGE"
        if not hasattr(extract_constants, message_name):
            continue
        code = getattr(extract_constants, name)
        message = getattr(extract_constants, message_name)
        assert isinstance(code, str) and code
        assert isinstance(message, str) and message
        pairs.append((code, message))
    assert pairs, "expected extract_constants CODE/MESSAGE pairs"
    return pairs


def _frontend_message_map() -> dict[str, str]:
    text = FE_EXTRACT_WARNINGS.read_text(encoding="utf-8")
    exported: dict[str, str] = {}
    for match in re.finditer(
        r"export const (?P<name>[A-Z0-9_]+_CODE) = '(?P<code>[^']+)' as const",
        text,
    ):
        exported[match.group("name")] = match.group("code")

    messages: dict[str, str] = {}
    for match in re.finditer(
        r"export const (?P<name>[A-Z0-9_]+_MESSAGE)\s*=\s*'(?P<msg>[^']*)'\s*as const",
        text,
        flags=re.MULTILINE,
    ):
        messages[match.group("name")] = match.group("msg")

    catalog: dict[str, str] = {}
    for match in re.finditer(
        r"\[(?P<code_const>[A-Z0-9_]+_CODE)\]:\s*(?P<msg_const>[A-Z0-9_]+_MESSAGE)",
        text,
    ):
        code_const = match.group("code_const")
        msg_const = match.group("msg_const")
        assert code_const in exported, f"missing FE export {code_const}"
        assert msg_const in messages, f"missing FE export {msg_const}"
        catalog[exported[code_const]] = messages[msg_const]
    assert catalog, "expected EXTRACT_WARNING_MESSAGES entries in frontend catalog"
    return catalog


def test_backend_extract_constants_are_registered_in_frontend_catalog() -> None:
    fe_catalog = _frontend_message_map()
    missing: list[str] = []
    mismatched: list[str] = []
    for code, message in _backend_code_message_pairs():
        if code not in fe_catalog:
            missing.append(code)
            continue
        if fe_catalog[code] != message:
            mismatched.append(f"{code}: fe={fe_catalog[code]!r} be={message!r}")
    assert not missing, f"FE extractWarnings missing BE codes: {missing}"
    assert not mismatched, f"FE/BE extract warning copy drift: {mismatched}"


def test_mvp_skeleton_preview_message_matches_frozen_backend_copy() -> None:
    fe_catalog = _frontend_message_map()
    assert fe_catalog[extract_constants.MVP_SKELETON_PREVIEW_CODE] == (extract_constants.MVP_SKELETON_PREVIEW_MESSAGE)
