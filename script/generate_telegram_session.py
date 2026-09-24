"""Generate a new TELEGRAM_SESSION using the repository's .env file."""

import asyncio
import os
from pathlib import Path
import sys


def main() -> int:
    # Direct script execution puts script/, not the repository, on sys.path.
    repository_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository_root))
    os.chdir(repository_root)

    from src.config.settings import settings
    from src.integration.telegram_session import generate_session

    print("Create a fresh Telegram session. Keep the generated value secret.")
    print("Use a separate generated session for each independently running worker.")
    try:
        phone = settings.telegram_phone.strip() or input("Telegram phone number (with +country code): ").strip()
        session = asyncio.run(generate_session(
            settings.telegram_api_id, settings.telegram_api_hash, phone
        ))
    except (KeyboardInterrupt, EOFError):
        print("\nSession generation cancelled.", file=sys.stderr)
        return 1
    except Exception as exc:
        # Do not expose configuration or authentication values in tracebacks.
        detail = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        print(f"Session generation failed: {detail}", file=sys.stderr)
        return 1

    print("\nCopy this line into .env or your deployment secret configuration:")
    print(f'TELEGRAM_SESSION="{session}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
