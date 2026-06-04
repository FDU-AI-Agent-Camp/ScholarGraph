"""MinerU pipeline simplified backend for short-PDF async head extraction."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.config import Settings, get_settings
from backend.ingest.head_candidates import HeadCandidate, parse_mineru_markdown

logger = logging.getLogger(__name__)

MINERU_BINARY = "mineru"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def is_mineru_available() -> bool:
    """Return True when ``mineru`` CLI is on PATH."""
    return shutil.which(MINERU_BINARY) is not None


def resolve_mineru_lang(pdf_path: Path, *, settings: Settings | None = None) -> str:
    """Resolve MinerU ``-l`` flag: configured value or CJK heuristic."""
    cfg = settings or get_settings()
    configured = cfg.ingest_mineru_lang.strip().lower()
    if configured in ("en", "ch"):
        return configured
    try:
        from backend.ingest.pdf import extract_pdf_text

        sample = extract_pdf_text(pdf_path, max_pages=2)
    except Exception:
        return "en"
    cjk_count = len(_CJK_RE.findall(sample))
    alpha_count = len(re.findall(r"[A-Za-z]", sample))
    if cjk_count > max(alpha_count // 4, 20):
        return "ch"
    return "en"


def _find_markdown_output(output_dir: Path, stem: str) -> Path | None:
    candidates = sorted(output_dir.rglob("*.md"))
    if not candidates:
        return None
    preferred = [path for path in candidates if stem in path.name]
    return preferred[0] if preferred else candidates[0]


def run_mineru_pipeline(
    pdf_path: Path,
    *,
    settings: Settings | None = None,
) -> HeadCandidate | None:
    """
    Run ``mineru -b pipeline -m txt -f false -t false`` and parse markdown head.

    Returns None when MinerU is unavailable or subprocess fails.
    """
    if not is_mineru_available():
        logger.info("MinerU CLI not found; skipping path B for %s", pdf_path.name)
        return None

    cfg = settings or get_settings()
    resolved = pdf_path.resolve()
    lang = resolve_mineru_lang(resolved, settings=cfg)
    env = os.environ.copy()
    if cfg.ingest_mineru_model_source.strip():
        env["MINERU_MODEL_SOURCE"] = cfg.ingest_mineru_model_source.strip()

    with tempfile.TemporaryDirectory(prefix="scholargraph-mineru-") as tmp:
        output_dir = Path(tmp)
        command = [
            MINERU_BINARY,
            "-b",
            "pipeline",
            "-m",
            "txt",
            "-f",
            "false",
            "-t",
            "false",
            "-l",
            lang,
            "-o",
            str(output_dir),
            str(resolved),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=cfg.ingest_mineru_timeout_seconds,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("MinerU timed out for %s", resolved.name)
            return None
        except OSError:
            logger.exception("MinerU subprocess failed for %s", resolved.name)
            return None

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            logger.warning(
                "MinerU exited %s for %s: %s",
                completed.returncode,
                resolved.name,
                stderr[:500],
            )
            return None

        md_path = _find_markdown_output(output_dir, resolved.stem)
        if md_path is None or not md_path.is_file():
            logger.warning("MinerU produced no markdown for %s", resolved.name)
            return None

        return parse_mineru_markdown(md_path.read_text(encoding="utf-8", errors="replace"))
