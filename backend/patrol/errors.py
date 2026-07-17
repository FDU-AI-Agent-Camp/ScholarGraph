# Copyright 2026 FDU-AI-Agent-Camp
# SPDX-License-Identifier: Apache-2.0

"""Patrol domain errors mapped to API error codes."""


class PatrolError(Exception):
    """Raised when patrol cannot complete; carries a stable API error code."""

    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
