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

    def test_parses_krw_market_asset_addition(self):
        message = make_message(
            "[거래] 카미노파이낸스(KMNO) KRW 마켓 디지털 자산 추가"
        )

        self.assertEqual(parse_upbit_telegram_notice(message), ["KMNO"])

    def test_rejects_krw_market_asset_addition_start_time_change(self):
        message = make_message(
            "[거래] 카미노파이낸스(KMNO) KRW 마켓 디지털 자산 추가 "
            "(거래지원 개시 시점 변경 안내)"
        )

        self.assertEqual(parse_upbit_telegram_notice(message), [])

    def test_rejects_krw_market_asset_addition_additional_change(self):
        message = make_message(
            "[거래] 카미노파이낸스(KMNO) KRW 마켓 디지털 자산 추가 "
            "(거래지원 개시 시점 추가 변경 안내)"
        )

        self.assertEqual(parse_upbit_telegram_notice(message), [])

    def test_rejects_unrelated_message(self):
        self.assertEqual(parse_upbit_telegram_notice(make_message("New listing")), [])


if __name__ == "__main__":
    unittest.main()
