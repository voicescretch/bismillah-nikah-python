import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Tambahkan root folder proyek ke sys.path agar seluruh modul 'bot' selalu terdeteksi di Vercel
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from telegram import Update
from telegram.ext import Application

try:
    from bot.config import DATABASE_URL, TELEGRAM_BOT_TOKEN, WEBHOOK_SECRET
    from bot.database import init_db
    from bot.handlers import setup_application
except Exception as e:
    logging.error("Gagal mengimpor modul bot: %s", e, exc_info=True)
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
    init_db = None
    setup_application = None

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

        if setup_application is None:
            raise RuntimeError("Modul bot.handlers gagal diimpor!")

        _telegram_app = setup_application(TELEGRAM_BOT_TOKEN)
        await _telegram_app.initialize()
        await _telegram_app.start()
        logger.info("Telegram bot Application initialized and started.")
    else:
        if not getattr(_telegram_app, "_initialized", True):
            await _telegram_app.initialize()
        if not _telegram_app.running:
            await _telegram_app.start()

    return _telegram_app


async def ensure_db_ready() -> str:
    """Memastikan tabel database siap saat request pertama."""
    global _db_initialized
    if not _db_initialized:
        if not DATABASE_URL:
            return "DATABASE_URL is empty"
        if init_db is None:
            return "bot.database module not loaded"
        try:
            await init_db()
            _db_initialized = True
            logger.info("Database schema initialized successfully.")
            return "connected & initialized"
        except Exception as e:
            logger.error("Error initializing database schema: %s", e, exc_info=True)
            return f"error: {str(e)}"
    return "connected"


@app.get("/")
@app.get("/api")
@app.get("/api/index")
async def health_check():
    """Endpoint diagnosa status bot, database & webhook status dari Telegram."""
    has_token = bool(TELEGRAM_BOT_TOKEN)
    has_db = bool(DATABASE_URL)
    has_secret = bool(WEBHOOK_SECRET)

    db_status = "untested"
    if has_db:
        try:
            db_status = await ensure_db_ready()
        except Exception as e:
            db_status = f"connection failed: {str(e)}"
    else:
        db_status = "DATABASE_URL belum diatur di Vercel"

    # Periksa status webhook live langsung dari Telegram API
    webhook_info_report = {}
    if has_token:
        try:
            telegram_app = await get_telegram_app()
            wh_info = await telegram_app.bot.get_webhook_info()
            webhook_info_report = {
                "registered_webhook_url": wh_info.url or "(Belum diatur / Kosong ❌)",
                "has_custom_certificate": wh_info.has_custom_certificate,
                "pending_update_count": wh_info.pending_update_count,
                "last_error_date": str(wh_info.last_error_date) if wh_info.last_error_date else None,
                "last_error_message": wh_info.last_error_message or "None (No errors reported by Telegram)",
                "status": "Webhook Terdaftar ✅" if wh_info.url else "Webhook Belum Didaftarkan ❌",
            }
        except Exception as e:
            webhook_info_report = {"error": f"Gagal mengambil info webhook: {str(e)}"}
    else:
        webhook_info_report = {"error": "TELEGRAM_BOT_TOKEN belum diset"}

    return {
        "status": "online",
        "service": "Bismillah Nikah Telegram Bot API",
        "environment_check": {
            "TELEGRAM_BOT_TOKEN": "SET ✅" if has_token else "MISSING ❌",
            "DATABASE_URL": "SET ✅" if has_db else "MISSING ❌",
            "WEBHOOK_SECRET": "SET ✅" if has_secret else "NOT SET (Optional)",
            "database_connection": db_status,
        },
        "telegram_webhook_status": webhook_info_report,
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
