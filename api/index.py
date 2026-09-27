import json
import logging
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from telegram import Update
from telegram.ext import Application

from bot.config import DATABASE_URL, TELEGRAM_BOT_TOKEN, WEBHOOK_SECRET
from bot.database import init_db
from bot.handlers import setup_application

# Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("BismillahNikahBot")

app = FastAPI(
    title="Bismillah Nikah Bot Webhook API",
    description="Serverless Telegram Bot Webhook Handler for Vercel",
    version="1.0.0",
)

# Global Telegram Application Instance
_telegram_app: Optional[Application] = None
_db_initialized: bool = False


async def get_telegram_app() -> Application:
    """Mengambil atau menginisialisasi singleton instance Application."""
    global _telegram_app
    if _telegram_app is None:
        if not TELEGRAM_BOT_TOKEN:
            logger.error("TELEGRAM_BOT_TOKEN belum diatur!")
            raise ValueError("TELEGRAM_BOT_TOKEN is missing in environment variables.")

        _telegram_app = setup_application(TELEGRAM_BOT_TOKEN)
        await _telegram_app.initialize()
        logger.info("Telegram bot Application initialized.")
    elif not _telegram_app.running and not getattr(_telegram_app, "_initialized", True):
        await _telegram_app.initialize()

    return _telegram_app


async def ensure_db_ready():
    """Memastikan tabel database siap saat request pertama."""
    global _db_initialized
    if not _db_initialized:
        try:
            await init_db()
            _db_initialized = True
            logger.info("Database schema initialized successfully.")
        except Exception as e:
            logger.error("Error initializing database schema: %s", e, exc_info=True)


@app.get("/")
@app.get("/api")
@app.get("/api/index")
async def health_check():
    """Endpoint diagnosa status bot & environment variables."""
    has_token = bool(TELEGRAM_BOT_TOKEN)
    has_db = bool(DATABASE_URL)
    has_secret = bool(WEBHOOK_SECRET)

    db_status = "untested"
    try:
        if has_db:
            await ensure_db_ready()
            db_status = "connected"
        else:
            db_status = "missing DATABASE_URL"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "online",
        "service": "Bismillah Nikah Telegram Bot API",
        "environment_check": {
            "TELEGRAM_BOT_TOKEN": "SET ✅" if has_token else "MISSING ❌",
            "DATABASE_URL": "SET ✅" if has_db else "MISSING ❌",
            "WEBHOOK_SECRET": "SET ✅" if has_secret else "NOT SET (Optional)",
            "database_connection": db_status,
        },
    }


@app.post("/")
@app.post("/api")
@app.post("/api/index")
@app.post("/api/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    """
    Endpoint pemroses webhook dari Telegram.
    Mendukung verifikasi secret token demi keamanan.
    """
    # Verifikasi Secret Token jika dikonfigurasi
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        logger.warning("Secret token tidak cocok! Ditolak.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret token",
        )

    try:
        # Pastikan DB siap
        await ensure_db_ready()

        # Baca data JSON dari Telegram
        body_bytes = await request.body()
        if not body_bytes:
            return Response(status_code=status.HTTP_200_OK, content="Empty body")

        req_body = json.loads(body_bytes.decode("utf-8"))

        telegram_application = await get_telegram_app()
        update = Update.de_json(req_body, telegram_application.bot)

        if update:
            await telegram_application.process_update(update)

        return Response(status_code=status.HTTP_200_OK, content="OK")

    except json.JSONDecodeError:
        logger.error("JSON tidak valid diterima.")
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Bad JSON")
    except Exception as e:
        logger.error("Exception saat memproses webhook Telegram: %s", e, exc_info=True)
        # Tetap kembalikan 200 OK agar Telegram tidak terus me-retry request yang error
        return Response(status_code=status.HTTP_200_OK, content="Error processed")
