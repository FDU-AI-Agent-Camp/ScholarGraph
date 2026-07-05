"""Strong paradigm signals mined outside the paper head (BE-1 extension)."""

from __future__ import annotations

import re

from backend.ingest.text_utils import normalize_for_sections, normalize_whitespace

MAX_CONCLUSION_CHARS = 1_500
MAX_META_CHARS = 300
CONCLUSION_TAIL_WINDOW = 3_000

# Conclusion / Discussion / 结论 / 讨论 headings, searched in the tail window only.
# Capture stops at obvious trailing sections so references/acknowledgments do not leak in.
_CONCLUSION_STOP_EN = (
    r"(?:^|\n)\s*(?:references|acknowledgments?|appendix|data\s+availability|"
    r"author\s+contributions|competing\s+interests)\b"
)
_CONCLUSION_STOP_ZH = (
    r"(?:^|\n)\s*(?:参考\s*文献|致\s*谢|附\s*录|数据\s*可用性|"
    r"利益\s*冲突|作者\s*贡献)\b"
)

_CONCLUSION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"(?is)(?:^|\n)\s*(?:conclusions?|discussion|summary|concluding\s+remarks?)\s*[:\-]?\s*\n+"
        rf"(.+?)(?={_CONCLUSION_STOP_EN}|{_CONCLUSION_STOP_ZH}|\Z)",
    ),
    re.compile(
        rf"(?is)(?:^|\n)\s*(?:[一二三四五六七八九十][、．.]\s*)?(?:结\s*论|讨\s*论|总\s*结|结\s*语)"
        rf"\s*[:：]?\s*\n+(.+?)(?={_CONCLUSION_STOP_EN}|{_CONCLUSION_STOP_ZH}|\Z)",
    ),
)

# Lightweight meta-information heuristics for paradigm classification signals.
_FUNDING_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Prefer quoted project names (strongest paradigm signal).
    re.compile(
        r"(?is)(?:基金项目|资助项目|项目资助|受\s*资\s*助|Funding|Fund(?:ed)?\s+by|"
        r"Financial\s+support|Grant|Supported\s+by)\s*[:：]\s*[^\n]{0,60}?[“\"《]([^”\"》]{5,200})[”\"》]",
    ),
    re.compile(
        r"(?is)(?:基金项目|资助项目|项目资助|受\s*资\s*助|Funding|Fund(?:ed)?\s+by|"
        r"Financial\s+support|Grant|Supported\s+by)\s*[:：]\s*(.+?)(?=\n|；|;|$)",
    ),
    re.compile(r"(?is)(?:项目编号|Project\s+No\.?|Grant\s+No\.?)\s*[:：]?\s*(.+?)(?=\n|；|;|$)"),
)

_AFFILIATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?is)(?:作者单位|工作单位|单位|Affiliations?)\s*[:：]\s*(.+?)(?=\n|；|;|$)",
    ),
    # Chinese author biographies often embed affiliations in a single sentence.
    # Capture the affiliation and role, stopping before "main research direction" filler.
    re.compile(
        r"(?i)作者简介\s*[：:]\s*[^\n。；;]*?((?:大学|学院|研究所|研究中心|博物馆|考古所|博物院)"
        r"[^\n。；;]{2,60}?)(?=主要研究|主要从事|E-mail|Email|通讯作者|[\n。；;]|$)",
    ),
    re.compile(
        r"(?is)(?:Department|Institute|University|College|School|Faculty)\s+of\s+[^\n]{5,200}",
    ),
)

_JOURNAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?is)(?:期刊|杂志|Journal|Proceedings)\s*[:：]\s*(.+?)(?=\n|$)"),
)

_JOURNAL_EXCLUDE_RE = re.compile(
    r"(?i)doi|http|www\.|vol\.|no\.|issue|page|article|received|accepted|published|"
    r"copyright|license|abstract|关键词|keywords",
)


def _trim_conclusion_paragraphs(body: str, *, max_paragraphs: int = 2) -> str:
    """Keep the final 1-2 paragraphs of a conclusion section."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    selected = paragraphs[-max_paragraphs:] if paragraphs else []
    joined = "\n\n".join(selected)
    return joined[:MAX_CONCLUSION_CHARS]


def extract_conclusion_tail(full_text: str, *, window: int = CONCLUSION_TAIL_WINDOW) -> str:
    """
    Anchor-extract the last 1-2 paragraphs of a Conclusion / Discussion / 结论 section.

    Searches only the trailing ``window`` characters to keep the operation cheap and avoid
    matching intermediate discussion sections in long papers.
    """
    if not full_text:
        return ""
    tail = full_text[-window:] if len(full_text) >= window else full_text
    normalized = normalize_for_sections(tail)
    if not normalized:
        return ""

    # Use the last match so that a final "结论" wins over an earlier "讨论".
    last_match: re.Match[str] | None = None
    for pattern in _CONCLUSION_PATTERNS:
        for match in pattern.finditer(normalized):
            last_match = match
    if last_match:
        body = normalize_whitespace(last_match.group(1))
        if body:
            return _trim_conclusion_paragraphs(body)
    return ""


def _first_line_match(patterns: tuple[re.Pattern[str], ...], text: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            line = match.group(1).strip() if match.lastindex else match.group(0).strip()
            line = re.sub(r"\s+", " ", line)
            line = re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", "", line)
            line = line.strip(" ;；，,")
            if line and len(line) >= 3:
                return line[:MAX_META_CHARS]
    return None


def _looks_like_journal_line(line: str) -> bool:
    """Heuristic for standalone journal names in the first few lines of a PDF."""
    stripped = line.strip()
    if not stripped or len(stripped) > 40:
        return False
    if _JOURNAL_EXCLUDE_RE.search(stripped):
        return False
    if re.search(
        r"(?i)journal|proceedings|transactions|review|letters|quarterly|"
        r"communications|magazine|学报|杂志|期刊|月刊|论丛|辑刊",
        stripped,
    ):
        return True
    if re.match(r"^[\u4e00-\u9fa5]{2,8}(?:研究|学报|杂志|刊|丛)$", stripped):
        return True
    return False


def extract_meta_info(text: str) -> dict[str, str]:
    """
    Lightweight regex extraction of journal / funding / affiliation signals.

    Returns a dict with keys ``journal``, ``funding``, ``affiliation``.
    These fields are intentionally heuristic and are used only as soft signals for
    paradigm classification.
    """
    result: dict[str, str] = {"journal": "", "funding": "", "affiliation": ""}
    if not text:
        return result

    funding = _first_line_match(_FUNDING_PATTERNS, text)
    if funding:
        result["funding"] = funding

    affiliation = _first_line_match(_AFFILIATION_PATTERNS, text)
    if affiliation:
        result["affiliation"] = affiliation

    journal = _first_line_match(_JOURNAL_PATTERNS, text)
    if journal:
        result["journal"] = journal
    else:
        normalized = normalize_for_sections(text)
        for raw_line in normalized.split("\n")[:20]:
            line = raw_line.strip()
            if _looks_like_journal_line(line):
                result["journal"] = line[:MAX_META_CHARS]
                break

    return result
