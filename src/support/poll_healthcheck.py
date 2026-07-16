import sys
import time
from pathlib import Path

from src.config.settings import settings


def poll_healthcheck_max_age_seconds() -> float:
    """Return the maximum expected gap between successful Upbit polls."""
    return (
        max(0.0, settings.scraper_cooldown)
        + abs(settings.scraper_cooldown_offset)
        + max(0.0, settings.scraper_timeout)
        + settings.poll_healthcheck_grace_seconds
    )


def record_poll_success(path: Path | None = None) -> None:
    """Refresh the heartbeat after Upbit returns a successful response."""
    heartbeat_path = path or settings.poll_healthcheck_file
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.touch(exist_ok=True)


def reset_poll_health(path: Path | None = None) -> None:
    """Remove a heartbeat left by a previous process start."""
    heartbeat_path = path or settings.poll_healthcheck_file
    heartbeat_path.unlink(missing_ok=True)


def check_poll_health(
    path: Path | None = None,
    now: float | None = None,
) -> tuple[bool, str]:
    heartbeat_path = path or settings.poll_healthcheck_file
    try:
        modified_at = heartbeat_path.stat().st_mtime
    except FileNotFoundError:
        return False, f"poll heartbeat does not exist: {heartbeat_path}"
    except OSError as exc:
        return False, f"poll heartbeat cannot be read: {exc}"

    checked_at = time.time() if now is None else now
    age_seconds = max(0.0, checked_at - modified_at)
    max_age_seconds = poll_healthcheck_max_age_seconds()
    if age_seconds > max_age_seconds:
        return (
            False,
            "poll heartbeat is stale: "
            f"age_seconds={age_seconds:.1f} max_age_seconds={max_age_seconds:.1f}",
        )

    return (
        True,
        "poll heartbeat is healthy: "
        f"age_seconds={age_seconds:.1f} max_age_seconds={max_age_seconds:.1f}",
    )


def main() -> int:
    healthy, message = check_poll_health()
    print(message, file=sys.stdout if healthy else sys.stderr)
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
