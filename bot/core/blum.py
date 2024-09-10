import asyncio
import random
from datetime import timedelta
from enum import Enum
from typing import Optional
from urllib import parse

import aiohttp
from bot.exceptions.blum import HtmlContentType
import pyrogram.types
from aiohttp import ContentTypeError
from pyrogram import Client
from aiocfscrape import CloudflareScraper
from fake_useragent import UserAgent
from pyrogram.raw.functions.channels import JoinChannel
from random_username.generate import generate_username
from pyrogram.raw.functions.messages import RequestWebView

from bot.config import settings
from bot.exceptions import ClaimRewardNextDay, NeedToStartFarm, UsernameNotAvailable, ReferralTokenUnavailable, \
    UserNotFound, AccountNotFound, TaskAlreadyClaimed, TaskNotComplete, CannotGetTasks, CannotStartGame, CannotGetTaskEvents, \
    HtmlContentType
    
from bot.models import AuthResponse, BalanceResponse, TelegramWebData, ClaimFarmingResponse, Farming, StartGameResponse, \
    Task
    
from bot.utils.logger import logger


class RequestMethods(str, Enum):
    POST = "POST"
    GET = "GET"
    PUT = "PUT"


def format_duration(seconds):
    duration_td = timedelta(seconds=seconds)
    hours, remainder = divmod(duration_td.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours)} hours {int(minutes)} minutes {int(seconds)} seconds"

def retry_async(max_retries=2, exception=Exception):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            session = args[0].session_name
            retries = 0
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except exception as e:
                    retries += 1
                    logger.error(f"Session {session} | Error: {e}. Retrying {retries}/{max_retries}...")
                    await asyncio.sleep(10)
                    if retries >= max_retries:
                        break
        return wrapper
    return decorator

class Blum:
    def __init__(self, tg_client: Client, proxy: Optional[str] = None):
        self.game_uri = "https://game-domain.blum.codes/api/v1"
        self.auth_uri = "https://user-domain.blum.codes/api/v1"

        self.telegram_web = "https://telegram.blum.codes"

        self.proxy = proxy

        self.session_name = tg_client.name
        self.client = tg_client
        self.refresh_token = ''

        self.session = CloudflareScraper(headers={"User-Agent": UserAgent(os="android").random},
                                         timeout=aiohttp.ClientTimeout(total=120))

        self.logger = logger.bind(session_name=f"{self.session_name: <10} | ")

    async def logout(self):
        await self.session.close()
        
    async def login(self, referral_code: str | list[str] = None) -> AuthResponse:
        payload = {"query": await self.get_telegram_web_data()}

        valid_referral_code = None

        if referral_code:
            if isinstance(referral_code, list):
                for referral_c in referral_code:
                    if not (await self.check_referral_code(referral_c)):
                        settings.REFERRAL_CODES.remove(referral_c)
                        self.logger.error(f"Referral code {referral_c} is invalid, please remove it from config")
                    else:
                        valid_referral_code = referral_c
            else:
                if not (await self.check_referral_code(referral_code)):
                    self.logger.error(
                        "Blum account not created and referral code not valid or already has 5 invites")
                    raise AccountNotFound(
                        "Blum account not created and referral code not valid or already has 5 invites")
                else:
                    valid_referral_code = referral_code

            if not valid_referral_code:
                self.logger.error("Failed to create account, no valid referral codes found")

            username = generate_username()[0]

            if not (await self.is_username_available(username)):
                return await self.login(valid_referral_code)

            payload["referralToken"] = valid_referral_code
            payload["username"] = username

        response = await self.__request(RequestMethods.POST,
                                        self.auth_uri + "/auth/provider/PROVIDER_TELEGRAM_MINI_APP",
                                        json=payload)
        parsed_response = AuthResponse(**response)

        if not parsed_response.access_token and not settings.REFERRAL_CODES:
            self.logger.error("Blum account not created and referral codes not provided")
            raise AccountNotFound("Blum account not created and referral codes not provided")

        if not parsed_response.access_token:
            self.logger.info("Creating Blum account")
            return await self.login(settings.REFERRAL_CODES)

        self.session.headers["Authorization"] = "Bearer " + parsed_response.access_token

        self.refresh_token = parsed_response.refresh_token

        if valid_referral_code:
            logger.success("Blum account created")
        return parsed_response

    async def is_username_available(self, username: str) -> bool:
        try:
            await self.__request(RequestMethods.POST, self.auth_uri + "/user/username/check",
                                 json={"username": username})
        except UsernameNotAvailable:
            return False
        return True

    async def check_referral_code(self, referral_code: str) -> bool:
        payload = {"query": await self.get_telegram_web_data(), "referralToken": referral_code}
        try:
            await self.__request(RequestMethods.POST,
                                 self.auth_uri + "/auth/provider/PROVIDER_TELEGRAM_MINI_APP",
                                 json=payload)
        except ReferralTokenUnavailable:
            return False
        return True

    async def create_account(self, username: str, referral_token: str) -> AuthResponse:
        payload = {"query": await self.get_telegram_web_data(), "username": username, "referralToken": referral_token}
        response = await self.__request(RequestMethods.POST,
                                        self.auth_uri + "/auth/provider/PROVIDER_TELEGRAM_MINI_APP",
                                        json=payload)
        return AuthResponse(**response)

    @retry_async()
    async def claim_daily_reward(self) -> bool:
        try:
            response = await self.__request(RequestMethods.POST, self.game_uri + "/daily-reward",
                                            params={"offset": -420})
            if response["message"] == "OK":
                self.logger.success(f"Daily reward claimed")
                return True
        except ClaimRewardNextDay:
            self.logger.debug(f"Daily reward already claimed")
        return False

    async def claim_farming(self) -> ClaimFarmingResponse:
        try:
            response = await self.__request(RequestMethods.POST, self.game_uri + "/farming/claim")
            self.logger.success(f"Farming claimed")
            return ClaimFarmingResponse(**response)
        except NeedToStartFarm:
            await self.start_farming()

    async def start_farming(self) -> Farming:
        response = await self.__request(RequestMethods.POST, self.game_uri + "/farming/start")
        self.logger.info(f"Farming started""")
        return Farming(**response)

    async def get_balance(self) -> BalanceResponse:
        response = await self.__request(RequestMethods.GET, self.game_uri + "/user/balance")
        return BalanceResponse(**response)

    @retry_async(exception=CannotStartGame)
    async def start_game(self) -> str:
        response = await self.__request(RequestMethods.POST, self.game_uri + "/game/play")
        self.logger.debug(f"Game started")
        return StartGameResponse(**response).game_id

    async def claim_game(self, game_id: str):
        points = random.randint(*[240, 280])  # todo add to config
        payload = {"gameId": game_id, "points": points}
        response = await self.__request(RequestMethods.POST, self.game_uri + "/game/claim", json=payload)
        if response["message"] == "OK":
            self.logger.success(f"Finish play in game! Reward: {points}")
        else:
            self.logger.error(f"Couldn't play game! Message: {response['message']}")

    async def play_game(self):
        game_id = await self.start_game()

        await asyncio.sleep(random.uniform(35, 40))

        await self.claim_game(game_id)
        
    @retry_async(exception=CannotGetTasks)
    async def get_tasks(self) -> list[Task]:
        response = await self.__request(RequestMethods.GET, self.game_uri + "/tasks")
        
        tasks = []
        for obj in response:
            tasks += obj["tasks"]

        return [Task(**task) for task in tasks]

    async def start_task(self, task_id: str) -> Optional[Task]:
        try:
            response = await self.__request(RequestMethods.POST, self.game_uri + f"/tasks/{task_id}/start")
            task = Task(**response)
            self.logger.debug(f"Task started {task_id} | Reward {task.reward}")
            return task
        except TaskAlreadyClaimed:
            self.logger.debug(f"Failed to start task {task_id} (already claimed)")
        return None
    
    @retry_async(exception=CannotGetTaskEvents)
    async def claim_task(self, task_id: str) -> Optional[Task]:
        await asyncio.sleep(random.uniform(10, 20))
        try:
            response = await self.__request(RequestMethods.POST, self.game_uri + f"/tasks/{task_id}/claim")
            task = Task(**response)
            self.logger.success(f"Successfully complete task | Reward {task.reward}")
        except TaskNotComplete:
            self.logger.error(f"Failed when claim task {task_id} | Task is not done")
        return None

    async def get_telegram_web_data(self) -> str:
        await self.client.connect()

        peer = await self.client.resolve_peer("BlumCryptoBot")

        if (await self.client.get_chat_history_count(peer.user_id)) == 0:
            await self.client.send_message("BlumCryptoBot", "/start")

        web_view: pyrogram.raw.base.WebViewResult = await self.client.invoke(RequestWebView(
            peer=peer,
            bot=peer,
            platform="android",
            from_bot_menu=False,
            url=self.telegram_web + "/"
        ))

        await self.client.disconnect()

        auth_url = web_view.url
        fragment = parse.urlparse(auth_url).fragment

        telegram_web_data: TelegramWebData = TelegramWebData(**parse.parse_qs(fragment))

        return telegram_web_data.tgWebAppData

    async def subscribe(self, url: str):
        await self.client.connect()
        channel = await self.client.resolve_peer(url.replace("https://t.me/", ""))
        await self.client.invoke(JoinChannel(channel=channel))
        await self.client.disconnect()

    async def refresh_tokens(self):
        response = await self.__request(RequestMethods.POST, self.auth_uri + "/auth/refresh",
                                        json={"refresh": self.refresh_token})
        parsed = AuthResponse(**response)

        self.session.headers["Authorization"] = "Bearer " + parsed.access_token
        self.refresh_token = parsed.refresh_token
    
    @retry_async(exception=HtmlContentType)
    async def __request(self, method: RequestMethods, url: str, **args) -> dict:
        response = await self.session.request(method, url, proxy=self.proxy, **args)
        settings.IS_DEV_MODE and print(await response.text())
        content_type = response.headers.get('Content-Type', '')

        if 'application/json' in content_type:
            try:
                jsoned: dict = await response.json()
            except ContentTypeError:
                raise Exception(await response.text())
            if type(jsoned) is dict and (error_message := jsoned.pop("message", None)) is not None:
                if error_message == "same day":
                    raise ClaimRewardNextDay(error_message)
                elif error_message == "Need to start farm":
                    raise NeedToStartFarm(error_message)
                elif error_message == "Username is not available":
                    raise UsernameNotAvailable(error_message)
                elif error_message == "referral token limit has been exceeded":
                    raise ReferralTokenUnavailable(error_message)
                elif error_message == "Current user is guest":
                    raise UserNotFound(error_message)
                elif error_message == "Task is already claimed":
                    raise TaskAlreadyClaimed(error_message)
                elif error_message == "Task is not done":
                    raise TaskNotComplete(error_message)
                elif error_message == "can not get task":
                    raise CannotGetTasks(error_message)
                elif error_message == "can not get task events":
                    raise CannotGetTaskEvents(error_message)
                elif error_message == "cannot start game":
                    raise CannotStartGame(error_message)
                raise Exception(error_message)
            return jsoned
        elif 'text/plain' in content_type:
            return {"message": await response.text()}
        elif "text/html" in content_type:
            raise HtmlContentType()
        else:
            raise Exception(f"Unexpected content type: {content_type}")

    async def run(self):
        await self.login()

        balance = await self.get_balance()

        self.logger.info(
            f"Balance: {balance.balance: <8} | Game Passes: {balance.game_passes: <3} | Farming: {'<c>finished</c>' if balance.farming and balance.farming.end < balance.now_timestamp else '<g>started</g>' if balance.farming else '<r>not started</r>'}")

        while True:
            if not balance.farming:
                await self.start_farming()
            elif balance.farming.end < balance.now_timestamp:
                await self.claim_farming()
                await asyncio.sleep(random.uniform(5, 10))
                await self.start_farming()

            if await self.claim_daily_reward():
                balance = await self.get_balance()
                self.logger.info(
                    f"Balance: {balance.balance: <8} | Game Passes: {balance.game_passes: <3} | Farming: {'<c>finished</c>' if balance.farming and balance.farming.end < balance.now_timestamp else '<g>started</g>' if balance.farming else '<r>not started</r>'}")

            balance = await self.get_balance()
            
            if settings.CLAIM_TASKS:
                tasks = await self.get_tasks()
                
                for task in tasks:
                    if task.status == task.Status.not_started \
                        and task.type != task.Type.progress_target \
                        and task.type != task.Type.wallet_connection \
                        and task.type != task.Type.internal \
                        :
                            await self.start_task(task.id)

                    elif task.status == task.Status.ready_for_claim:  
                        await self.claim_task(task.id)

            if balance.game_passes > 0 and settings.PLAY_GAMES:
                self.logger.info(f"Find Game Passes, start gaming")
                for _ in range(balance.game_passes):
                    await asyncio.sleep(random.uniform(10, 20))
                    await self.play_game()

                await asyncio.sleep(random.uniform(5, 10))

            if balance.farming and balance.farming.end > balance.now_timestamp:
                sleep_duration = (balance.farming.end - balance.now_timestamp) // 1000 + 1
                self.logger.info(f"Farm sleep {format_duration(sleep_duration)}")
                await asyncio.sleep(sleep_duration)
                await self.login()


async def run_blum(tg_client: Client, proxy: Optional[str] = None):
    runtime = Blum(tg_client, proxy)
    await runtime.run()
