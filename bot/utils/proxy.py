from better_proxy import Proxy

from bot.config import settings


def get_proxies() -> list[Proxy]:
    if settings.USE_PROXY_FROM_FILE:
        with open(file='bot/config/proxies.txt', encoding='utf-8-sig') as file:
            proxies = [Proxy.from_str(proxy=row.strip()).as_url for row in file]
    else:
        proxies = []

    return proxies
