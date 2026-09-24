import re
from src.control.event.telegram_controller import TelegramMessage

BITHUMB_LISTING_PREFIX = "[마켓 추가]"
BITHUMB_MARKET_NAMES = {"원화": "KRW", "비트코인": "BTC"}


def parse_upbit_telegram_notice(message:TelegramMessage) -> list[str]:
    text = message.text
    headline = text.splitlines()[0].strip() if text else ""

    # 거래 = "Trading"
    if headline.startswith("[거래]"): 
        # 신규 거래지원 안내 = "New trading support announcement"
        asset_section, separator, market_section = headline.partition("신규 거래지원 안내")
        if separator:
            market_match = re.search(r"\(([^()]*)\)\s*$", market_section)
            if not market_match:
                return []
            
            markets = set(re.findall(r"\b[A-Z]{2,10}\b", market_match.group(1)))
            if "KRW" not in markets:
                return []
            
        else:
            # Match the market list separately from the addition phrase so notices
            # such as "KRW, USDT 마켓 디지털 자산 추가" are also accepted.
            addition_phrase = re.search(
                r"마켓\s*디지털\s*자산\s*추가\s*$", headline
            )
            if not addition_phrase:
                return []

            market_section = headline[:addition_phrase.start()]
            markets = set(re.findall(r"\b[A-Z]{2,10}\b", market_section))
            if "KRW" not in markets:
                return []

            asset_section = headline[:addition_phrase.start()]

        # 거래 = "Trading"
        asset_section = asset_section.removeprefix("[거래]").strip()

    else:
        return []

    asset_list = []
    for match in re.finditer(
        r"(?:^|,\s*)(?P<asset_name>[^,()]+?)\s*\((?P<symbol>[A-Z0-9]+)\)",
        asset_section,
    ):
        asset_list.append(match.group("symbol"))
    
    return asset_list

def parse_bithumb_telegram_notice(message:TelegramMessage) -> list[str]:
    text = message.text

    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines or not lines[0].startswith(BITHUMB_LISTING_PREFIX):
        return []

    headline = lines[0].removeprefix(BITHUMB_LISTING_PREFIX).strip()
    listing_match = re.fullmatch(r"(?P<assets>.+\))\s+(?P<markets>.+?)\s*마켓\s*추가(?:\s*안내)?", headline)
    if not listing_match:
        return []

    markets_text = listing_match.group("markets")
    markets = [
        market
        for label, market in BITHUMB_MARKET_NAMES.items()
        if label in markets_text
    ]
    markets.extend(re.findall(r"\b(?:KRW|BTC|USDT)\b", markets_text.upper()))
    if "KRW" not in markets:
        return []

    assets = []
    for match in re.finditer(
        r"(?P<asset_name>[^,()]+?)\s*\((?P<symbol>[A-Z0-9]+)\)",
        listing_match.group("assets"),
    ):
        assets.append(match.group("symbol"))

    return assets
