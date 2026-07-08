import httpx

from app.core.config import get_settings


def mask_token(token: str) -> str:
    return token[:4] + "..." + token[-4:] if len(token) > 8 else "***"


async def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.telegram_api_base}/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    return response.status_code == 200
