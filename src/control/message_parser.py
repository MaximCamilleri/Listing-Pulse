import re
from src.control.telegram_controller import TelegramMessage


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
            # KRW 마켓 디지털 자산 추가 = "Digital asset added to the KRW market"
            addition_phrase = re.search(r"KRW\s*마켓\s*디지털\s*자산\s*추가", headline)
            if not addition_phrase:
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