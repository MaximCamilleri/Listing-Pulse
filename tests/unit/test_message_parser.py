import unittest
from datetime import datetime, timezone

from src.control.message_parser import parse_upbit_telegram_notice
from src.integration.telegram_integration import TelegramMessage


def make_message(text: str) -> TelegramMessage:
    return TelegramMessage(
        channel_id=123,
        channel_title="Listings",
        message_id=456,
        sender_id=None,
        text=text,
        date=datetime.now(timezone.utc),
        has_media=False,
        grouped_id=None,
    )


class MessageParserTests(unittest.TestCase):
    def test_parses_symbols_from_new_krw_trading_notice(self):
        message = make_message(
            "[거래] 비트코인 (BTC), 이더리움 (ETH) "
            "신규 거래지원 안내 (KRW, BTC, USDT)"
        )

        self.assertEqual(
            parse_upbit_telegram_notice(message),
            ["BTC", "ETH"],
        )

    def test_rejects_notice_without_krw_market(self):
        message = make_message(
            "[거래] 비트코인 (BTC) 신규 거래지원 안내 (BTC, USDT)"
        )

        self.assertEqual(parse_upbit_telegram_notice(message), [])

    def test_rejects_unrelated_message(self):
        self.assertEqual(parse_upbit_telegram_notice(make_message("New listing")), [])


if __name__ == "__main__":
    unittest.main()
