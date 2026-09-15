import logging
import signal
import time

from app import create_app
from app.services.scheduler import start_scheduler, stop_scheduler


logger = logging.getLogger("oncall.scheduler")
_shutdown = False


def _handle_shutdown(signum, frame):
    """Handle container shutdown signals."""

    global _shutdown
    _shutdown = True

    logger.info(
        "scheduler worker shutdown requested",
        extra={"extra": {"signal": signum}},
    )


def main():
    """Start Beacon scheduler worker."""
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    app = create_app(log_role="scheduler")

    logger.info("scheduler worker started")

    with app.app_context():
        start_scheduler()

        while not _shutdown:
            time.sleep(1)

        stop_scheduler(wait=False)

    logger.info("scheduler worker stopped")


if __name__ == "__main__":
    main()
