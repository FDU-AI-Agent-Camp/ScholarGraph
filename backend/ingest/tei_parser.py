"""Parse GROBID TEI XML into header fields (§2.1 path B, long PDF)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from backend.ingest.head_candidates import HeadCandidate
from backend.ingest.snippets import normalize_whitespace

TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}
_MAX_FIELD_CHARS = 4_000


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text_content(element: ET.Element | None) -> str:
    if element is None:
        return ""
    parts = [chunk.strip() for chunk in element.itertext() if chunk and chunk.strip()]
    return normalize_whitespace(" ".join(parts))


def _find_first(root: ET.Element, local_name: str) -> ET.Element | None:
    for element in root.iter():
        if _local_tag(element.tag) == local_name:
            return element
    return None


def _find_all(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local_tag(element.tag) == local_name]


def _parse_title(header: ET.Element) -> str:
    title_stmt = _find_first(header, "titleStmt")
    if title_stmt is None:
        return ""
    title_el = _find_first(title_stmt, "title")
    return _text_content(title_el)[:_MAX_FIELD_CHARS]


def _parse_abstract(header: ET.Element) -> str:
    profile = _find_first(header, "profileDesc")
    if profile is None:
        return ""
    abstract_el = _find_first(profile, "abstract")
    return _text_content(abstract_el)[:_MAX_FIELD_CHARS]


def _parse_keywords(header: ET.Element) -> str:
    profile = _find_first(header, "profileDesc")
    if profile is None:
        return ""
    terms: list[str] = []
    for keywords_el in _find_all(profile, "keywords"):
        for term in _find_all(keywords_el, "term"):
            value = _text_content(term)
            if value:
                terms.append(value)
    if terms:
        return ", ".join(terms)[:_MAX_FIELD_CHARS]
    for text_class in _find_all(profile, "textClass"):
        for keyword in _find_all(text_class, "keyword"):
            value = _text_content(keyword)
            if value:
                terms.append(value)
    return ", ".join(terms)[:_MAX_FIELD_CHARS]


def _parse_intro(body: ET.Element) -> str:
    paragraphs: list[str] = []
    for div in _find_all(body, "div"):
        head_el = _find_first(div, "head")
        head_text = _text_content(head_el).lower()
        if head_text and not re.search(r"intro|introduction|引言|前言", head_text, re.IGNORECASE):
            if paragraphs:
                break
            continue
        for paragraph in _find_all(div, "p"):
            text = _text_content(paragraph)
            if text:
                paragraphs.append(text)
            if sum(len(part) for part in paragraphs) >= _MAX_FIELD_CHARS:
                break
        if paragraphs:
            break

    if not paragraphs:
        for paragraph in _find_all(body, "p"):
            text = _text_content(paragraph)
            if text:
                paragraphs.append(text)
            if len(paragraphs) >= 3:
                break

    joined = " ".join(paragraphs).strip()
    return joined[:_MAX_FIELD_CHARS]


def parse_tei_to_head_candidate(tei_xml: str) -> HeadCandidate:
    """Convert GROBID ``processFulltextDocument`` TEI into merge-ready fields."""
    root = ET.fromstring(tei_xml)
    header = _find_first(root, "teiHeader") or root
    body = _find_first(root, "body")
    intro = _parse_intro(body) if body is not None else ""
    return HeadCandidate(
        title=_parse_title(header),
        abstract=_parse_abstract(header),
        keywords=_parse_keywords(header),
        intro=intro,
        source="grobid",
    )
