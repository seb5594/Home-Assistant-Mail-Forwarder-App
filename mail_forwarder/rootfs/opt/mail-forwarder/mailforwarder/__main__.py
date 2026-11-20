"""Entry point: ``python3 -m mailforwarder``."""
import asyncio
import json

from . import settings
from .app import Application, configure_logging, run_forever


def _log_level() -> str:
    try:
        return json.loads(settings.OPTIONS_FILE.read_text()).get("log_level", "info")
    except (OSError, ValueError):
        return "info"


def main() -> None:
    configure_logging(_log_level())
    asyncio.run(run_forever(Application()))


if __name__ == "__main__":
    main()
