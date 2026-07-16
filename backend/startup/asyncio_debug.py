"""Development / CI guards against false-async blocking of the event loop."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_SLOW_CALLBACK_SECONDS = 0.1


def configure_asyncio_block_detector(
    loop: asyncio.AbstractEventLoop | None = None,
    *,
    slow_callback_seconds: float | None = None,
    force: bool = False,
) -> bool:
    """Enable ``loop.set_debug`` + ``slow_callback_duration`` when configured.

    Returns True when the detector was enabled. Production leaves
    ``ASYNCIO_SLOW_CALLBACK_MS=0`` (disabled) so logs stay quiet.
    """
    from backend.config import get_settings

    settings = get_settings()
    if slow_callback_seconds is None:
        millis = float(settings.asyncio_slow_callback_ms)
        if millis < 0:
            # Auto: enable only outside staging/production.
            millis = 100.0 if settings.app_env in {"development", "test"} else 0.0
        if millis <= 0 and not force:
            return False
        slow_callback_seconds = (millis / 1000.0) if millis > 0 else DEFAULT_SLOW_CALLBACK_SECONDS
    if slow_callback_seconds <= 0:
        return False

    target = loop or asyncio.get_running_loop()
    target.set_debug(True)
    target.slow_callback_duration = slow_callback_seconds
    logger.info(
        "asyncio_block_detector_enabled",
        extra={
            "slow_callback_seconds": slow_callback_seconds,
            "app_env": settings.app_env,
        },
    )
    return True
