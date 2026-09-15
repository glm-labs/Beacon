import os

from app import create_app
from app.services.scheduler import start_scheduler


app = create_app()


def _debug_enabled() -> bool:
    return str(os.getenv("BEACON_FLASK_DEBUG", "")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


if __name__ == "__main__":
    start_scheduler()
    app.run(
        host=os.getenv("BEACON_HOST", "0.0.0.0"),
        port=int(os.getenv("BEACON_PORT", "8080")),
        debug=_debug_enabled(),
    )
