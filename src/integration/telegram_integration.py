from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias
from uuid import uuid4
from telethon import TelegramClient, events, types, utils

from src.support.logger import get_logger
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

@dataclass(frozen=True, slots=True)
class _Subscription:
    """
    Internal subscription information required to remove a Telethon handler.
    """
    callback: Callable
    event_builder: events.NewMessage

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
        session_name: str = "telegram_listener",
        phone: str | None = None,
        telegram_connection_retries: int = 5,
        telegram_retry_delay: float = 5.0,
        supervisor_initial_delay: float = 2.0,
        supervisor_max_delay: float = 60.0,
    ) -> None:
        if api_id <= 0:
            raise ValueError("api_id must be a positive integer")

        if not api_hash:
            raise ValueError("api_hash cannot be empty")

        if supervisor_initial_delay <= 0:
            raise ValueError("supervisor_initial_delay must be positive")

        if supervisor_max_delay < supervisor_initial_delay:
            raise ValueError(
                "supervisor_max_delay must be greater than or equal to "
                "supervisor_initial_delay"
            )

        self._phone = phone
        self._supervisor_initial_delay = supervisor_initial_delay
        self._supervisor_max_delay = supervisor_max_delay

        self._client = TelegramClient(
            session=session_name,
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

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected()

    @property
    def is_running(self) -> bool:
        return self._running

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

        event_builder = events.NewMessage(chats=channel)

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

        self._client.add_event_handler(
            telethon_callback,
            event_builder,
        )

        self._subscriptions[subscription_id] = _Subscription(
            callback=telethon_callback,
            event_builder=event_builder,
        )

        logger.info(
            "Registered Telegram channel subscription",
            extra={
                "subscription_id": subscription_id,
                "channel": channel,
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

        logger.info("Connecting to Telegram")

        await self._client.start(phone=self._phone)

        logger.info("Connected to Telegram")

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

        reconnect_delay = self._supervisor_initial_delay

        try:
            while not self._stop_event.is_set():
                try:
                    await self.start()

                    # A successful connection resets the outer backoff.
                    reconnect_delay = self._supervisor_initial_delay

                    logger.info("Telegram listener is running")

                    await self._client.run_until_disconnected()

                    if not self._stop_event.is_set():
                        logger.warning(
                            "Telegram client disconnected unexpectedly"
                        )

                except asyncio.CancelledError:
                    raise

                except Exception:
                    if self._stop_event.is_set():
                        break

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

            if self._client.is_connected():
                await self._client.disconnect()

            logger.info("Telegram integration stopped")

    async def stop(self) -> None:
        """
        Request shutdown and disconnect the client.

        Disconnecting releases run_until_disconnected(), allowing the
        run_forever() coroutine to finish.
        """

        self._stop_event.set()

        if self._client.is_connected():
            await self._client.disconnect()

    async def _wait_before_reconnect(self, delay: float) -> None:
        """
        Sleep before reconnecting, while still allowing immediate shutdown.
        """

        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=delay,
            )
        except TimeoutError:
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


