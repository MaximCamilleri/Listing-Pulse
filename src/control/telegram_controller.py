from src.integration.telegram_integration import TelegramIntegration, ChannelReference, TelegramMessage
from collections.abc import Callable, Awaitable
import asyncio

from src.support.logger import get_logger
logger = get_logger(__name__)

MessageHandler = Callable[[TelegramMessage], Awaitable[None]]

class TelegramController:
    """
    Application controller for one Telegram channel.

    Responsibilities:
        - Select the channel to monitor.
        - Subscribe through TelegramIntegration.
        - Buffer incoming messages.
        - Process messages sequentially.
        - Apply domain/business rules.
        - Isolate business-processing failures.
        - Coordinate graceful shutdown.
    """

    def __init__(
        self,
        *,
        telegram_kwargs: dict,
        channel: ChannelReference,
        message_handler: MessageHandler,
        queue_size: int = 1_000,
    ) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")

        self._telegram = TelegramIntegration(**telegram_kwargs)
        self._channel = channel
        self._message_handler = message_handler

        self._message_queue: asyncio.Queue[TelegramMessage | None] = (
            asyncio.Queue(maxsize=queue_size)
        )

        self._subscription_id: str | None = None
        self._worker_task: asyncio.Task[None] | None = None

        self._accepting_messages = False
        self._running = False
        self._stop_lock = asyncio.Lock()

    async def run(self) -> None:
        """
        Start the controller and block until it is stopped.
        """

        if self._running:
            raise RuntimeError("TelegramChannelController is already running")

        self._running = True
        self._accepting_messages = True

        self._subscription_id = self._telegram.subscribe_to_new_messages(
            channel=self._channel,
            handler=self._receive_message,
        )

        self._worker_task = asyncio.create_task(
            self._message_worker(),
            name="telegram-business-logic-worker",
        )

        logger.info(
            "Telegram channel controller started",
            extra={"channel": self._channel},
        )

        try:
            await self._telegram.run_forever()
        finally:
            await self.stop()

    async def stop(self) -> None:
        """
        Stop receiving messages, disconnect Telegram, and drain queued work.
        """

        worker_task: asyncio.Task[None] | None = None

        async with self._stop_lock:
            if not self._running:
                return

            self._accepting_messages = False

            if self._subscription_id is not None:
                self._telegram.unsubscribe(self._subscription_id)
                self._subscription_id = None

            await self._telegram.stop()

            if self._worker_task is not None:
                # None is a sentinel placed after existing queued messages.
                # The worker therefore finishes already-accepted work first.
                await self._message_queue.put(None)

                worker_task = self._worker_task
                self._worker_task = None

            self._running = False

        if worker_task is not None:
            await worker_task

        logger.info(
            "Telegram channel controller stopped",
            extra={"channel": self._channel},
        )

    async def _receive_message(self, message: TelegramMessage) -> None:
        """
        Lightweight integration callback.

        No business logic should run here. Queueing keeps the Telethon event
        handler responsive and gives the controller explicit backpressure.
        """

        if not self._accepting_messages:
            return

        await self._message_queue.put(message)

    async def _message_worker(self) -> None:
        """
        Consume queued messages and apply business logic sequentially.
        """

        while True:
            message = await self._message_queue.get()

            try:
                if message is None:
                    return

                await self._message_handler(message)

            except asyncio.CancelledError:
                raise

            except Exception:
                # A malformed message or downstream failure should not terminate
                # the controller. In production, send this to error monitoring.
                logger.exception(
                    "Message handler logic failed",
                    extra={
                        "channel_id": (
                            message.channel_id
                            if message is not None
                            else None
                        ),
                        "message_id": (
                            message.message_id
                            if message is not None
                            else None
                        ),
                    },
                )

            finally:
                self._message_queue.task_done()