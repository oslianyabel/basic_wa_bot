import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime

import sentry_sdk
from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel

from config import config
from core import notifications
from core.agent import Agent
from core.prompt import json_tools
from core.tools import available_tools
from logging_conf import logger


def check_time(last_time):
    performance = time.time() - last_time
    if performance > 25:
        logger.warning(f"Performance of the API: {performance}")
    else:
        logger.debug(f"Performance of the API: {performance}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )
    # Start background cleanup task
    global _cleanup_task
    _cleanup_task = asyncio.create_task(_cleanup_inactive())

    yield

    # Stop background cleanup task
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await asyncio.gather(_cleanup_task, return_exceptions=True)
        except Exception:
            pass


app = FastAPI(lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)


bot = Agent("Legal Agent")
WORDS_LIMIT = config.WORDS_LIMIT or 1500
users_in_process: dict[str, bool] = {}
wait_msg_index: dict[str, int] = {}

# Inactivity cleanup configuration and state
INACTIVITY_TTL_SECONDS: int = getattr(
    config, "INACTIVITY_TTL_SECONDS", 24 * 60 * 60
)  # 24 horas
CLEANUP_INTERVAL_SECONDS: int = getattr(
    config, "CLEANUP_INTERVAL_SECONDS", 60 * 60
)  # 1 hora
last_activity: dict[str, float] = {}
_cleanup_task: asyncio.Task | None = None


def end_interaction(user_number, last_time):
    users_in_process[user_number] = False
    check_time(last_time)
    return {"status": "ok"}


class HealthCheckResponse(BaseModel):
    status: str
    timestamp: str
    service: str


@app.get("/health", response_model=HealthCheckResponse)
def health_check() -> HealthCheckResponse:
    return HealthCheckResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        service="WhatsApp Webhook API",
    )


@app.get("/whatsapp")
async def verify_webhook(request: Request):
    """Verify webhook for Meta WhatsApp API"""
    try:
        mode = request.query_params.get("hub.mode")
        challenge = request.query_params.get("hub.challenge")
        token = request.query_params.get("hub.verify_token")

        # Use the same verify token from config or set a new one
        verify_token_expected = getattr(config, "WHATSAPP_VERIFY_TOKEN", "vibecode")

        if mode == "subscribe" and token == verify_token_expected:
            logger.info("WEBHOOK VERIFIED for Meta WhatsApp API")
            return int(challenge)  # type: ignore
        else:
            logger.warning(
                f"Webhook verification failed - Mode: {mode}, Token match: {token == verify_token_expected}"
            )
            raise HTTPException(status_code=403, detail="Forbidden")
    except Exception as e:
        logger.error(f"Error in webhook verification: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ============================================================================
# WEBHOOK MESSAGE PROCESSING FUNCTIONS
# ============================================================================


async def parse_webhook_data(request: Request) -> dict | None:
    """Parse and validate incoming webhook data from Meta WhatsApp API.

    Returns:
        dict: Parsed webhook data or None if parsing fails
    """
    try:
        webhook_data = await request.json()
        logger.debug(f"Webhook data received: {webhook_data}")
        return webhook_data
    except Exception as e:
        logger.error(f"Error parsing webhook data: {e}")
        return None


def extract_message_content(webhook_data: dict) -> tuple[str, str, str] | None:
    """Extract user number and message content from webhook data.

    Args:
        webhook_data: Raw webhook data from Meta WhatsApp API

    Returns:
        tuple: (user_number, message_content, message_id) or None if extraction fails
    """
    try:
        entry = webhook_data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})

        # Check if this is a message event
        messages = value.get("messages")
        if not messages:
            logger.debug("No messages in webhook data")
            return None

        message = messages[0]
        user_number = message.get("from", "")
        message_id = message.get("id", "")

        # Extract message text based on message type
        incoming_msg = _extract_text_from_message(message)

        if not incoming_msg:
            logger.warning("No text message found or unsupported message type")
            return None

        return user_number, incoming_msg, message_id

    except (IndexError, KeyError) as e:
        logger.error(f"Error extracting message data: {e}")
        return None


def _extract_text_from_message(message: dict) -> str:
    """Extract text content from different message types.

    Args:
        message: Message object from webhook data

    Returns:
        str: Extracted text content
    """
    message_type = message.get("type")

    if message_type == "text":
        return message.get("text", {}).get("body", "").strip()

    elif message_type == "interactive":
        interactive = message.get("interactive", {})
        interactive_type = interactive.get("type")

        if interactive_type == "button_reply":
            return interactive.get("button_reply", {}).get("title", "")
        elif interactive_type == "list_reply":
            return interactive.get("list_reply", {}).get("title", "")

    return ""


async def check_user_availability(user_number: str) -> bool:
    """Check if user is available for new conversation.

    Args:
        user_number: Original user number

    Returns:
        bool: True if user is available, False if busy
    """
    if users_in_process.get(user_number):
        logger.warning(f"Usuario {user_number} en proceso")

        # Mensajes alternativos
        wait_messages = [
            "Porfa dame un segundo para terminar de elaborar la respuesta 🕒",
            "Un momento, estoy procesando tu pedido — te respondo enseguida ⏳",
            "Disculpa la demora, estoy trabajando para darte la mejor respuesta 🤏",
            "Estoy revisando la información; te escribo en breve 📡",
            "Gracias por la paciencia — preparando tu respuesta ahora mismo 🔄",
        ]

        # Obtener índice actual para el usuario, por defecto 0
        idx = wait_msg_index.get(user_number, 0)
        msg = wait_messages[idx % len(wait_messages)]

        # Enviar mensaje y actualizar índice (siguiente vez se usará el siguiente)
        asyncio.create_task(
            notifications.send_whatsapp_message(body=msg, to=user_number)
        )
        wait_msg_index[user_number] = (idx + 1) % len(wait_messages)
        return False

    return True


async def _cleanup_inactive() -> None:
    """Periodically clean inactive users and bots to prevent memory growth."""
    while True:
        try:
            now = time.time()
            to_remove: list[str] = []

            for phone, ts in list(last_activity.items()):
                if now - ts > INACTIVITY_TTL_SECONDS and not users_in_process.get(
                    phone, False
                ):
                    to_remove.append(phone)

            for phone in to_remove:
                bot.chat_memory.delete_chat(phone)
                last_activity.pop(phone, None)
                logger.debug(f"Cleaned inactive session for {phone}")
        except Exception as exc:
            logger.error(f"Cleanup task error: {exc}")
        finally:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break


async def gen_ai_msg(
    message: str,
    user_number: str,
) -> str | None:
    """Generate AI response for user message.

    Args:
        user_number: Original user number

    Returns:
        str: AI output or None if error occurred
    """
    try:
        ai_msg = await bot.async_process_msg(
            message=message,
            user_id=user_number,
            rag_functions=available_tools,
            rag_prompt=json_tools,
        )
        return ai_msg
    except Exception as exc:
        logger.error(f"AI generation failed: {exc}")
        bot.chat_memory.delete_chat(user_number)
        asyncio.create_task(
            notifications.send_whatsapp_message(
                "Ha ocurrido un error y el chat fue reiniciado. Por favor, comencemos de nuevo",
                user_number,
            )
        )
        return None


async def send_ai_msg(ai_msg: str, user_number: str) -> None:
    """Send AI response to user, handling message length limits.

    Args:
        response: AI generated response
        user_number: User's phone number
    """
    if len(ai_msg) <= WORDS_LIMIT:
        asyncio.create_task(notifications.send_whatsapp_message(ai_msg, user_number))
        return

    # Handle long messages by splitting them
    logger.warning(
        "Respuesta fragmentada por exceder el límite de caracteres de Twilio"
    )

    start = 0
    while start < len(ai_msg):
        end = min(start + WORDS_LIMIT, len(ai_msg))

        # Try to break at newline to avoid cutting words
        if end < len(ai_msg) and ai_msg[end] != "\n":
            newline_pos = ai_msg.rfind("\n", start, end)
            if newline_pos > start:
                end = newline_pos

        chunk = ai_msg[start:end].strip()
        asyncio.create_task(notifications.send_whatsapp_message(chunk, user_number))
        start = end + 1 if ai_msg[end : end + 1] == "\n" else end


# ============================================================================
# MAIN WEBHOOK ENDPOINT
# ============================================================================


@app.post("/whatsapp")
async def whatsapp_reply(request: Request, background_tasks: BackgroundTasks):
    """Main endpoint for handling WhatsApp webhook messages.

    This endpoint processes incoming WhatsApp messages, manages user state,
    generates AI responses, and sends replies back to users.
    """
    start_time = time.time()
    logger.debug("=" * 125)

    # Parse incoming webhook data
    webhook_data = await parse_webhook_data(request)
    if not webhook_data:
        return {"status": "error"}

    # Extract message content
    message_data = extract_message_content(webhook_data)
    if not message_data:
        return {"status": "ok"}

    user_number, incoming_msg, message_id = message_data
    if message_id:
        asyncio.create_task(notifications.mark_whatsapp_message_as_read(message_id))

    if not await check_user_availability(user_number):
        check_time(start_time)
        return {"status": "ok"}

    users_in_process[user_number] = True
    try:
        logger.info(f"User {user_number}: {incoming_msg}")

        ai_msg = await gen_ai_msg(incoming_msg, user_number)
        if not ai_msg:
            logger.error("AI response generation returned None")
            return {"status": "ok"}

        await send_ai_msg(ai_msg, user_number)
        return {"status": "ok"}
    finally:
        users_in_process[user_number] = False
        last_activity[user_number] = time.time()
        check_time(start_time)
