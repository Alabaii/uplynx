import logging

from app.core.config import get_settings
from app.core.observability import init_sentry, start_metrics_server
from app.services.checks import run_http_check
from app.services.queue import HTTP_QUEUE
from app.workers.base import consume_forever


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_sentry("worker-http")
    start_metrics_server()
    consume_forever(HTTP_QUEUE, run_http_check, concurrency=get_settings().http_concurrency)
