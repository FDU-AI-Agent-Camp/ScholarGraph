"""Service-layer errors mapped to API / workflow error codes."""

from __future__ import annotations

PIPELINE_FAILED_CODE = "PIPELINE_FAILED"
INVALID_STATE_TRANSITION_CODE = "INVALID_STATE_TRANSITION"


class ServiceError(Exception):
    """Raised when a domain service fails; carries a stable error code for the workflow."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class InvalidStateTransitionError(ServiceError):
    """Paper / pipeline status machine rejected an illegal transition."""

    def __init__(
        self,
        message: str,
        *,
        from_status: str,
        to_status: str,
        paper_id: str | None = None,
    ) -> None:
        super().__init__(INVALID_STATE_TRANSITION_CODE, message)
        self.from_status = from_status
        self.to_status = to_status
        self.paper_id = paper_id
