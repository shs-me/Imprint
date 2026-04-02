import httpx
from loguru import logger

from ... import Config


class RestEngine:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            base_url=Config.UserConfig.rest,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )

    async def run_rest_engine(self):
        pass

    async def get_exchange_info(self):
        try:
            response = await self.client.get("/fapi/v1/exchangeInfo")
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"REST Error (Exchange Info): {e}")
            return None

    async def get_server_time(self):
        try:
            response = await self.client.get("/fapi/v1/time")
            response.raise_for_status()
            return response.json()["serverTime"]
        except Exception as e:
            logger.error(f"REST Error (Server Time): {e}")
            return None

    async def close(self):
        await self.client.aclose()
