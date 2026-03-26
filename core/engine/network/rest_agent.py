import httpx
from loguru import logger


class RestModule:
    def __init__(
        self,
        cfg,
    ):
        self.cfg = cfg

        self.client = httpx.AsyncClient(
            base_url=cfg["urls"]["rest"],
            timeout=5.0,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )

    async def run_rest_engine(
        self,
    ):
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


def rest_run(cfg, sem):
    logger.remove()

    logger.add(
        f"logs/{__name__}.log",
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {name}:{function}:{line} - {message}",
    )
