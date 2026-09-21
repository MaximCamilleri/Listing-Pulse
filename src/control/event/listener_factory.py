"""Build inactive listeners; the runtime interface owns their lifecycle."""

from typing import Literal

from src.config.settings import settings
from src.control.event.telegram_controller import MessageHandler, TelegramController
from src.integration.telegram_integration import TelegramIntegration

EVENT_CHANNELS = Literal["UPBIT", "BITHUMB"]


def listener_factory(channel: EVENT_CHANNELS, trigger_action: MessageHandler, *, telegram: TelegramIntegration | None = None) -> TelegramController:
    channels = {
        "UPBIT": settings.upbit_telegram_channel,
        "BITHUMB": settings.bithumb_telegram_channel,
    }
    if channel not in channels:
        raise ValueError(f"Unsupported event source: {channel}")
    return _setup_listener(channels[channel], trigger_action, telegram=telegram)


def _setup_listener(channel: str, trigger_action: MessageHandler, *, telegram: TelegramIntegration | None = None) -> TelegramController:
    telegram_kwargs = {
        "session_string" : settings.telegram_session,
        "api_id" : settings.telegram_api_id,
        "api_hash" : settings.telegram_api_hash,
        "phone" : settings.telegram_phone,
        "telegram_connection_retries" : settings.telegram_connection_retries,
        "telegram_retry_delay" : settings.telegram_retry_delay,
        "supervisor_initial_delay" : settings.telegram_supervisor_initial_delay,
        "supervisor_max_delay" : settings.telegram_supervisor_max_delay,
        "healthcheck_interval_seconds" : settings.healthcheck_interval_seconds,
        "readiness_max_wait_seconds" : settings.telegram_readiness_max_wait_seconds,
    }

    return TelegramController(
        telegram_kwargs=telegram_kwargs,
        channel=channel,
        message_handler=trigger_action,
        telegram=telegram,
    )
