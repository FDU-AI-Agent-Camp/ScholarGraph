# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Peripheral packages that may host sync→async bridges (Phase-3 Option A).

Adapters here are the **only** backend location intended to embed
``async_bridge.run_async`` for PaperService APIs. Core
``backend/services`` / ``backend/patrol`` must stay await-only.
"""
