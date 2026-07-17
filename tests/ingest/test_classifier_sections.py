# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Classifier section format round-trip."""

from backend.ingest.snippets import (
    format_classifier_input,
    parse_classifier_sections,
)


def test_format_and_parse_classifier_sections_round_trip() -> None:
    formatted = format_classifier_input(
        title="My Title",
        abstract="My abstract.",
        keywords="kw1, kw2",
        intro="Intro paragraph.",
    )
    sections = parse_classifier_sections(formatted)
    assert sections.title == "My Title"
    assert sections.abstract == "My abstract."
    assert sections.keywords == "kw1, kw2"
    assert sections.intro == "Intro paragraph."
