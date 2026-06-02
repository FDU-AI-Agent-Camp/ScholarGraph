"""Service-layer errors mapped to API / workflow error codes."""

PIPELINE_FAILED_CODE = "PIPELINE_FAILED"


class ServiceError(Exception):
    """Raised when a domain service fails; carries a stable error code for the workflow."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
