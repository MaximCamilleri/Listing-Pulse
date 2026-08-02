from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import time
from typing import TypeAlias
from uuid import uuid4
from telethon import TelegramClient, events, types, utils
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from src.config.settings import settings
from src.support.logger import get_logger
from src.support.healthcheck import record_health
logger = get_logger(__name__)

ChannelReference: TypeAlias = str | int


@dataclass(frozen=True, slots=True)
class TelegramMessage:
    """
    Application-facing representation of a Telegram message.
    The controller does not receive Telethon event objects directly, standardizing communication
    """
    channel_id: int | None
    channel_title: str | None
    message_id: int
    sender_id: int | None
    text: str
    date: datetime
    has_media: bool
    grouped_id: int | None

class TelegramListenerState(StrEnum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    RESOLVING_CHANNEL = "RESOLVING_CHANNEL"
    READY = "READY"
    WAITING_FOR_FLOOD_LIMIT = "WAITING_FOR_FLOOD_LIMIT"
    STOPPING = "STOPPING"


@dataclass(slots=True)
class _Subscription:
    """
    Internal subscription information required to remove a Telethon handler.
    """
    callback: Callable
    channel: ChannelReference
    event_builder: events.NewMessage | None = None

MessageHandler: TypeAlias = Callable[[TelegramMessage], Awaitable[None]]

class TelegramIntegration:
    """
    Infrastructure adapter around Telethon.

    Responsibilities:
        - Create and own the TelegramClient.
        - Authenticate and maintain the Telegram session.
        - Register and remove event handlers.
        - Convert Telethon events into application-facing messages.
        - Keep the connection alive.
        - Reconnect after unexpected disconnects.
        - Shut down cleanly.

    It deliberately contains no domain or business logic.
    """

    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        session_string: str,
        phone: str | None = None,
        telegram_connection_retries: int = 5,
        telegram_retry_delay: float = 5.0,
        supervisor_initial_delay: float = 2.0,
        supervisor_max_delay: float = 60.0,
        healthcheck_interval_seconds: float = 15.0,
        readiness_max_wait_seconds: float = 900.0,
    ) -> None:
        if api_id <= 0:
            raise ValueError("api_id must be a positive integer")

        if not api_hash:
            raise ValueError("api_hash cannot be empty")

        if not session_string or not session_string.strip():
            raise ValueError("session_string cannot be empty")

        if supervisor_initial_delay <= 0:
            raise ValueError("supervisor_initial_delay must be positive")

        if supervisor_max_delay < supervisor_initial_delay:
            raise ValueError(
                "supervisor_max_delay must be greater than or equal to "
                "supervisor_initial_delay"
            )

        if healthcheck_interval_seconds <= 0:
            raise ValueError("healthcheck_interval_seconds must be positive")

        if readiness_max_wait_seconds <= 0:
            raise ValueError("readiness_max_wait_seconds must be positive")

        self._phone = phone
        self._supervisor_initial_delay = supervisor_initial_delay
        self._supervisor_max_delay = supervisor_max_delay
        self._healthcheck_interval_seconds = healthcheck_interval_seconds
        self._readiness_max_wait_seconds = readiness_max_wait_seconds

        self._client = TelegramClient(
            session=StringSession(session_string.strip()),
            api_id=api_id,
            api_hash=api_hash,
            auto_reconnect=True,
            connection_retries=telegram_connection_retries,
            retry_delay=telegram_retry_delay,
            # Preserve Telegram update ordering. The registered callbacks should
            # remain lightweight; the controller delegates slow work to a queue.
            sequential_updates=True,
        )

        self._subscriptions: dict[str, _Subscription] = {}
        self._stop_event = asyncio.Event()
        self._running = False
        self._state = TelegramListenerState.DISCONNECTED
        self._state_changed_at = time.monotonic()

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def state(self) -> TelegramListenerState:
        return self._state

    def subscribe_to_new_messages(
        self,
        channel: ChannelReference,
        handler: MessageHandler,
    ) -> str:
        """
        Register an asynchronous callback for new messages in a channel.

        Args:
            channel:
                A public username such as "some_channel", a t.me URL, or a
                numeric Telegram channel ID.
            handler:
                An async application callback.

        Returns:
            An opaque subscription ID that can later be passed to unsubscribe().
        """

        channel = _normalize_channel_reference(channel)

        async def telethon_callback(event: events.NewMessage.Event) -> None:
            try:
                application_message = await self._convert_message(event)
                await handler(application_message)
            except asyncio.CancelledError:
                raise
            except Exception:
                # One callback failure should not kill the Telegram update loop.
                logger.exception(
                    "Unhandled exception in Telegram message callback",
                    extra={
                        "channel_id": getattr(event, "chat_id", None),
                        "message_id": getattr(event, "id", None),
                    },
                )

        subscription_id = uuid4().hex

        self._subscriptions[subscription_id] = _Subscription(
            callback=telethon_callback,
            channel=channel,
        )

        logger.info(
            "Configured Telegram channel subscription",
            extra={
                "subscription_id": subscription_id,
                "channel": channel,
                "channel_reference_type": (
                    "numeric" if isinstance(channel, int) else "username_or_url"
                ),
            },
        )

        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a previously registered subscription.

        Returns True when a subscription existed and was removed.
        """

        subscription = self._subscriptions.pop(subscription_id, None)

        if subscription is None:
            return False

        if subscription.event_builder is not None:
            self._client.remove_event_handler(
                subscription.callback,
                subscription.event_builder,
            )

        logger.info(
            "Removed Telegram channel subscription",
            extra={"subscription_id": subscription_id},
        )

        return True

    async def start(self) -> None:
        """
        Connect and authenticate the Telegram client.

        On the first execution, Telethon may prompt for a phone number, login
        code, and two-factor-authentication password. Subsequent executions use
        the saved session file.
        """

        if self._client.is_connected():
            return

        self._set_state(TelegramListenerState.CONNECTING)
        logger.info("Connecting to Telegram")

        await self._client.start(phone=self._phone)

        logger.info("Connected to Telegram")

    async def _activate_subscriptions(self) -> None:
        """Resolve configured channels and register handlers before readiness."""
        for subscription_id, subscription in self._subscriptions.items():
            if subscription.event_builder is not None:
                continue

            channel = subscription.channel
            resolved_channel = channel
            if isinstance(channel, str):
                self._set_state(TelegramListenerState.RESOLVING_CHANNEL)
                logger.info(
                    "Resolving Telegram channel subscription",
                    extra={"subscription_id": subscription_id},
                )
                resolved_channel = await self._client.get_input_entity(channel)

            event_builder = events.NewMessage(chats=resolved_channel)
            self._client.add_event_handler(
                subscription.callback,
                event_builder,
            )
            subscription.event_builder = event_builder
            logger.info(
                "Activated Telegram channel subscription",
                extra={
                    "subscription_id": subscription_id,
                    "channel_reference_type": (
                        "numeric" if isinstance(channel, int) else "resolved"
                    ),
                },
            )

    async def run_forever(self) -> None:
        """
        Keep the Telegram connection and event processing alive.

        Telethon first performs its own configured reconnection attempts. If
        run_until_disconnected() returns or raises after those attempts, this
        method applies an outer exponential-backoff reconnect loop.
        """

        if self._running:
            raise RuntimeError("TelegramIntegration is already running")

        self._running = True
        self._stop_event.clear()
        heartbeat_task = asyncio.create_task(
            self._run_health_heartbeat(),
            name="telegram-health-heartbeat",
        )

        reconnect_delay = self._supervisor_initial_delay

        try:
            while not self._stop_event.is_set():
                try:
                    await self.start()
                    await self._activate_subscriptions()
                    self._set_state(TelegramListenerState.READY)
                    record_health()

                    # Readiness, rather than a bare TCP connection, proves that
                    # the listener can safely reset its recovery backoff.
                    reconnect_delay = self._supervisor_initial_delay

                    logger.info("Telegram listener is ready")

                    await self._client.run_until_disconnected()

                    if not self._stop_event.is_set():
                        logger.warning(
                            "Telegram client disconnected unexpectedly"
                        )

                except FloodWaitError as exc:
                    if self._stop_event.is_set():
                        break
                    wait_seconds = max(float(exc.seconds), 0.0)
                    operation = (
                        "resolve_channel_subscription"
                        if self._state
                        is TelegramListenerState.RESOLVING_CHANNEL
                        else "connect_or_authenticate"
                    )
                    self._set_state(
                        TelegramListenerState.WAITING_FOR_FLOOD_LIMIT
                    )
                    logger.warning(
                        "Telegram rate limit encountered during listener "
                        "startup; waiting before retry",
                        extra={
                            "flood_wait_seconds": wait_seconds,
                            "operation": operation,
                        },
                    )
                    await self._wait_before_reconnect(wait_seconds)
                    continue

                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    externally_cancelled = bool(
                        current_task is not None and current_task.cancelling()
                    )
                    if self._stop_event.is_set() or externally_cancelled:
                        raise
                    self._set_state(TelegramListenerState.DISCONNECTED)
                    logger.exception(
                        "Telegram cancelled an in-flight operation "
                        "unexpectedly; recovering",
                        extra={"retry_delay_seconds": reconnect_delay},
                    )

                except Exception:
                    if self._stop_event.is_set():
                        break

                    self._set_state(TelegramListenerState.DISCONNECTED)
                    logger.exception(
                        "Telegram connection failed; reconnecting",
                        extra={"retry_delay_seconds": reconnect_delay},
                    )

                if self._stop_event.is_set():
                    break

                await self._wait_before_reconnect(reconnect_delay)

                reconnect_delay = min(
                    reconnect_delay * 2,
                    self._supervisor_max_delay,
                )

        finally:
            self._running = False
            self._set_state(TelegramListenerState.STOPPING)
            heartbeat_task.cancel()

            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            if self._client.is_connected():
                await self._client.disconnect()

            self._set_state(TelegramListenerState.DISCONNECTED)
            logger.info("Telegram integration stopped")

    async def _run_health_heartbeat(self) -> None:
        """Refresh health only while the client and event loop are responsive."""
        logger.info(
            "Telegram health heartbeat task started "
            "interval_seconds=%s healthcheck_file=%s",
            self._healthcheck_interval_seconds,
            settings.healthcheck_file,
        )

        last_health_eligible: bool | None = None

        while not self._stop_event.is_set():
            try:
                connected = self._client.is_connected()
                health_eligible = self._health_is_eligible(connected)

                if health_eligible != last_health_eligible:
                    logger.info(
                        "Telegram health state changed connected=%s "
                        "listener_state=%s health_eligible=%s",
                        connected,
                        self._state,
                        health_eligible,
                    )
                    last_health_eligible = health_eligible

                if health_eligible:
                    record_health()
                    logger.debug("Telegram health heartbeat refreshed")

            except Exception:
                logger.exception("Telegram health heartbeat refresh failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._healthcheck_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    def _health_is_eligible(
        self,
        connected: bool,
        *,
        now: float | None = None,
    ) -> bool:
        if not connected:
            return False
        if self._state is TelegramListenerState.READY:
            return True
        recoverable_not_ready = self._state in {
            TelegramListenerState.CONNECTING,
            TelegramListenerState.RESOLVING_CHANNEL,
            TelegramListenerState.WAITING_FOR_FLOOD_LIMIT,
        }
        current_time = time.monotonic() if now is None else now
        recovery_deadline = (
            self._state_changed_at + self._readiness_max_wait_seconds
        )
        return (
            recoverable_not_ready
            and current_time <= recovery_deadline
        )

    async def stop(self) -> None:
        """
        Request shutdown and disconnect the client.

        Disconnecting releases run_until_disconnected(), allowing the
        run_forever() coroutine to finish.
        """

        self._stop_event.set()
        self._set_state(TelegramListenerState.STOPPING)

        if self._client.is_connected():
            await self._client.disconnect()

    def _set_state(self, state: TelegramListenerState) -> None:
        if state is self._state:
            return
        previous = self._state
        self._state = state
        self._state_changed_at = time.monotonic()
        logger.info(
            "Telegram listener state changed",
            extra={
                "previous_state": previous,
                "listener_state": state,
            },
        )

    async def _wait_before_reconnect(self, delay: float) -> None:
        """
        Sleep before reconnecting, while still allowing immediate shutdown.
        """

        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=delay,
            )
        except asyncio.TimeoutError:
            pass

    @staticmethod
    async def _convert_message(
        event: events.NewMessage.Event,
    ) -> TelegramMessage:
        """
        Convert a Telethon event into an integration-neutral data object.
        """

        message = event.message

        # Event properties may not always contain the complete chat entity.
        # get_chat() resolves it from the cache or Telegram when necessary.
        chat = await event.get_chat()

        return TelegramMessage(
            channel_id=event.chat_id,
            channel_title=getattr(chat, "title", None),
            message_id=message.id,
            sender_id=message.sender_id,
            text=message.raw_text or "",
            date=message.date,
            has_media=message.media is not None,
            grouped_id=message.grouped_id,
        )


def _normalize_channel_reference(channel: ChannelReference) -> ChannelReference:
    """Convert raw channel IDs into Telethon's marked channel-ID format."""
    if not isinstance(channel, (str, int)) or isinstance(channel, bool):
        raise TypeError("channel must be a username, URL, or numeric ID")

    if isinstance(channel, str):
        channel = channel.strip()
        if not channel:
            raise ValueError("channel cannot be empty")

        try:
            channel_id = int(channel)
        except ValueError:
            return channel
    else:
        channel_id = channel

    if channel_id == 0:
        raise ValueError("numeric channel ID cannot be zero")

    # Telethon marks channel IDs as -(10**12 + raw_id). Configuration often
    # contains the raw ID with an optional leading minus, as returned by other
    # Telegram tools, so normalize both forms here.
    if channel_id <= -1_000_000_000_000:
        return channel_id

    return utils.get_peer_id(types.PeerChannel(abs(channel_id)))


