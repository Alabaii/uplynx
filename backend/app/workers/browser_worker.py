import asyncio
import logging

from app.core.config import get_settings
from app.core.observability import init_sentry, start_metrics_server
from app.schemas import CheckTask
from app.services.checks import run_browser_check
from app.services.queue import BROWSER_QUEUE
from app.workers.base import consume_forever

semaphore = asyncio.Semaphore(get_settings().browser_concurrency)


async def limited_browser_check(task: CheckTask) -> dict:
    async with semaphore:
        return await run_browser_check(task)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_sentry("worker-browser")
    start_metrics_server()
    consume_forever(BROWSER_QUEUE, limited_browser_check)
