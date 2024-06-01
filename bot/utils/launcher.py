import argparse
import asyncio
from itertools import cycle

from pyrogram import Client

from bot.core import register_sessions
from bot.core.blum import run_blum
from bot.utils.logger import logger
from bot.utils.proxy import get_proxies
from bot.utils.session import get_session_names, get_tg_clients

start_text = """
██████╗ ██╗     ██╗   ██╗███╗   ███╗    ██████╗  ██████╗ ████████╗
██╔══██╗██║     ██║   ██║████╗ ████║    ██╔══██╗██╔═══██╗╚══██╔══╝
██████╔╝██║     ██║   ██║██╔████╔██║    ██████╔╝██║   ██║   ██║
██╔══██╗██║     ██║   ██║██║╚██╔╝██║    ██╔══██╗██║   ██║   ██║
██████╔╝███████╗╚██████╔╝██║ ╚═╝ ██║    ██████╔╝╚██████╔╝   ██║
╚═════╝ ╚══════╝ ╚═════╝ ╚═╝     ╚═╝    ╚═════╝  ╚═════╝    ╚═╝

Select an action:

    1. Create session
    2. Run clicker
"""


async def process() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--action', type=int, help='Action to perform')

    max_name_len = 0
    for name in get_session_names():
        max_name_len = max(max_name_len, len(name))

    logger.info(f"Detected {len(get_session_names())} sessions | {len(get_proxies())} proxies")

    action = parser.parse_args().action

    if not action:
        print(start_text)

        while True:
            action = input("> ")

            if not action.isdigit():
                logger.warning("Action must be number")
            elif action not in ['1', '2']:
                logger.warning("Action must be 1 or 2")
            else:
                action = int(action)
                break

    if action == 1:
        await register_sessions()
    elif action == 2:
        tg_clients = await get_tg_clients()

        await run_tasks(tg_clients=tg_clients)


async def run_tasks(tg_clients: list[Client]):
    proxies = get_proxies()
    proxies_cycle = cycle(proxies) if proxies else None
    tasks = [asyncio.create_task(run_blum(tg_client=tg_client, proxy=next(proxies_cycle) if proxies_cycle else None))
             for tg_client in tg_clients]

    await asyncio.gather(*tasks)
