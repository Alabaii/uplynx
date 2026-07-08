from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import decrypt_secret, encrypt_secret
from app.models import TelegramIntegration, User
from app.schemas import TelegramConnect, TelegramRead, TelegramTestResponse
from app.services.telegram import mask_token, send_telegram_message

router = APIRouter()


@router.get("", response_model=TelegramRead)
def read_integration(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramRead:
    integration = db.scalar(select(TelegramIntegration).where(TelegramIntegration.user_id == user.id))
    if not integration:
        return TelegramRead(connected=False)
    return TelegramRead(
        connected=True,
        chat_id=integration.chat_id,
        alert_scopes=integration.alert_scopes,
        bot_token_masked=mask_token(decrypt_secret(integration.bot_token_secret)),
    )


@router.post("/connect", response_model=TelegramRead)
def connect(
    payload: TelegramConnect,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramRead:
    integration = db.scalar(select(TelegramIntegration).where(TelegramIntegration.user_id == user.id))
    if integration:
        integration.bot_token_secret = encrypt_secret(payload.bot_token)
        integration.chat_id = payload.chat_id
        integration.alert_scopes = payload.alert_scopes
    else:
        integration = TelegramIntegration(
            user_id=user.id,
            bot_token_secret=encrypt_secret(payload.bot_token),
            chat_id=payload.chat_id,
            alert_scopes=payload.alert_scopes,
        )
        db.add(integration)
    db.commit()
    return TelegramRead(
        connected=True,
        chat_id=payload.chat_id,
        alert_scopes=payload.alert_scopes,
        bot_token_masked=mask_token(payload.bot_token),
    )


@router.post("/test", response_model=TelegramTestResponse)
async def test(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TelegramTestResponse:
    integration = db.scalar(select(TelegramIntegration).where(TelegramIntegration.user_id == user.id))
    if not integration:
        return TelegramTestResponse(ok=False, detail="Telegram is not connected")
    ok = await send_telegram_message(
        decrypt_secret(integration.bot_token_secret),
        integration.chat_id,
        "PWA Monitor test notification",
    )
    return TelegramTestResponse(ok=ok, detail="sent" if ok else "Telegram API rejected test message")
