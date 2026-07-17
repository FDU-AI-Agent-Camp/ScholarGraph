# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""PDF ingest and text extraction (BE-1)."""

from backend.ingest.pdf import IngestResult, ingest_pdf

__all__ = ["IngestResult", "ingest_pdf"]
