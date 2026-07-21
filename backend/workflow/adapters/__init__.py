# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Sync adapters that explicitly bridge onto async PaperService APIs."""

from backend.workflow.adapters.paper_service_sync import PaperServiceSyncAdapter

__all__ = ["PaperServiceSyncAdapter"]
