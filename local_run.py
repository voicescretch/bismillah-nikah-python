"""
Script untuk menjalankan bot secara lokal (Long Polling) saat pengembangan.
Gunakan: python local_run.py
"""
import asyncio
import logging
import sys

from bot.database import init_db
from bot.handlers import setup_application

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("BismillahNikahBot-Local")


async def main():
    logger.info("Menginisialisasi Database...")
    try:
        await init_db()
        logger.info("Database berhasil terhubung & tabel siap.")
    except Exception as e:
        logger.error("Gagal menghubungkan database: %s", e)
        logger.error("Pastikan DATABASE_URL di file .env sudah benar.")
        sys.exit(1)

    logger.info("Menjalankan Telegram Bot dalam mode Long Polling...")
    app = setup_application()

    # Hapus webhook lama jika sebelumnya dipasang webhook
    await app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook lama berhasil dihapus. Memulai polling...")

    # Jalankan polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    logger.info("Bot 'Bismillah Nikah' aktif! Tekan Ctrl+C untuk berhenti.")
    try:
        # Loop selamanya hingga interupsi
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Menghentikan bot...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        logger.info("Bot telah berhenti.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
