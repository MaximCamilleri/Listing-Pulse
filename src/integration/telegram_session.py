"""Interactive provisioning of a fresh Telegram user session."""

from getpass import getpass

from telethon import TelegramClient
from telethon.sessions import StringSession


async def generate_session(api_id: int, api_hash: str, phone: str) -> str:
    """Authenticate a new in-memory session, export it, and disconnect."""
    if api_id <= 0 or not api_hash.strip():
        raise ValueError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH before running this script.")
    if not phone.strip().startswith("+") or not phone.strip()[1:].isdigit():
        raise ValueError("Use a phone number with country code, for example +35612345678.")

    client = TelegramClient(
        StringSession(), api_id, api_hash.strip(), receive_updates=False
    )
    try:
        await client.start(
            phone=phone.strip(),
            code_callback=lambda: getpass("Telegram login code: "),
            password=lambda: getpass("Telegram two-step verification password: "),
        )
        session = client.session.save()
        if not session:
            raise RuntimeError("Telegram did not return a session.")
        return session
    finally:
        # Logging out would revoke the session we just generated.
        await client.disconnect()
