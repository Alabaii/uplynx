import logging

from app.services.checks import run_http_check
from app.services.queue import HTTP_QUEUE
from app.workers.base import consume_forever


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    consume_forever(HTTP_QUEUE, run_http_check)
