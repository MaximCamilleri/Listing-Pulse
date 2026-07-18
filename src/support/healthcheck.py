import sys
import time
from pathlib import Path

from src.config.settings import settings


def record_health(path: Path | None = None) -> None:
    """Refresh the worker heartbeat after confirming Telegram is connected."""
    heartbeat_path = path or settings.healthcheck_file
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.touch(exist_ok=True)


def reset_health(path: Path | None = None) -> None:
    """Remove a heartbeat left by an earlier process in the same filesystem."""
    heartbeat_path = path or settings.healthcheck_file
    heartbeat_path.unlink(missing_ok=True)


def check_health(
    path: Path | None = None,
    *,
    now: float | None = None,
    max_age_seconds: float | None = None,
) -> tuple[bool, str]:
    heartbeat_path = path or settings.healthcheck_file
    allowed_age = (
        settings.healthcheck_max_age_seconds
        if max_age_seconds is None
        else max_age_seconds
    )

    if allowed_age <= 0:
        return False, "heartbeat max age must be positive"

    try:
        modified_at = heartbeat_path.stat().st_mtime
    except FileNotFoundError:
        return False, f"heartbeat does not exist: {heartbeat_path}"
    except OSError as exc:
        return False, f"heartbeat cannot be read: {exc}"

    checked_at = time.time() if now is None else now
    age_seconds = max(0.0, checked_at - modified_at)
    if age_seconds > allowed_age:
        return (
            False,
            "heartbeat is stale: "
            f"age_seconds={age_seconds:.1f} max_age_seconds={allowed_age:.1f}",
        )

    return (
        True,
        "heartbeat is healthy: "
        f"age_seconds={age_seconds:.1f} max_age_seconds={allowed_age:.1f}",
    )


def main() -> int:
    healthy, message = check_health()
    print(message, file=sys.stdout if healthy else sys.stderr)
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
