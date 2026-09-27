import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from telegram import Update

from bot.config import TELEGRAM_BOT_TOKEN, WEBHOOK_SECRET
from bot.database import init_db
from bot.handlers import setup_application

# Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("BismillahNikahBot")

# Inisialisasi Application Telegram
telegram_app = setup_application()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager untuk inisialisasi bot dan database."""
    logger.info("Memulai aplikasi serverless...")
    try:
        # Inisialisasi database schema jika belum ada
        await init_db()
        logger.info("Database berhasil diinisialisasi.")
    except Exception as e:
        logger.error("Gagal inisialisasi database: %s", e)

    # Inisialisasi Telegram Application
    await telegram_app.initialize()
    logger.info("Telegram bot initialized.")

    yield

    # Shutdown
    await telegram_app.shutdown()
    logger.info("Telegram bot shutdown.")


app = FastAPI(
    title="Bismillah Nikah Bot Webhook API",
    description="Serverless Telegram Bot Webhook Handler for Vercel",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
@app.get("/api")
@app.get("/api/index")
async def health_check():
    """Endpoint status & health check."""
    return {
        "status": "online",
        "service": "Bismillah Nikah Bot API",
        "framework": "FastAPI + python-telegram-bot v20+",
        "platform": "Vercel Serverless",
    }


@app.post("/")
@app.post("/api")
@app.post("/api/index")
@app.post("/api/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=None),
):
    """
    Endpoint pemroses webhook dari Telegram.
    Mendukung verifikasi secret token demi keamanan.
    """
    # Verifikasi Secret Token jika dikonfigurasi
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        logger.warning("Secret token tidak valid atau tidak cocok!")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret token",
        )

    try:
        # Baca payload JSON dari Telegram
        req_body = await request.json()
        update = Update.de_json(req_body, telegram_app.bot)

        if update:
            # Proses update secara asynchronous
            await telegram_app.process_update(update)

        return Response(status_code=status.HTTP_200_OK, content="OK")

    except json.JSONDecodeError:
        logger.error("Invalid JSON payload diterima.")
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Bad Request")
    except Exception as e:
        logger.error("Error saat memproses webhook: %s", e, exc_info=True)
        # Tetap kembalikan 200 OK agar Telegram tidak terus mengulang pengiriman
        return Response(status_code=status.HTTP_200_OK, content="OK")
