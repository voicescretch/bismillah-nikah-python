"""
Script utilitas untuk mengatur atau menghapus Telegram Webhook ke Vercel.
Penggunaan:
  python set_webhook.py set https://your-project.vercel.app/api
  python set_webhook.py info
  python set_webhook.py delete
"""
import asyncio
import sys
from telegram import Bot
from bot.config import TELEGRAM_BOT_TOKEN, WEBHOOK_SECRET


async def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN belum diatur di file .env!")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)

    if len(sys.argv) < 2 or sys.argv[1] not in ["set", "info", "delete"]:
        print("Penggunaan:")
        print("  python set_webhook.py set https://your-vercel-app.vercel.app/api")
        print("  python set_webhook.py info")
        print("  python set_webhook.py delete")
        return

    command = sys.argv[1]

    if command == "set":
        if len(sys.argv) < 3:
            print("❌ Harap masukkan URL webhook Vercel kamu.")
            print("Contoh: python set_webhook.py set https://bismillah-nikah.vercel.app/api")
            return
        url = sys.argv[2].strip()
        print(f"📡 Mengatur Webhook ke: {url} ...")
        success = await bot.set_webhook(
            url=url,
            secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET else None,
            drop_pending_updates=True,
        )
        if success:
            print("✅ Webhook berhasil diatur!")
        else:
            print("❌ Gagal mengatur webhook.")

    elif command == "info":
        print("🔍 Mengambil informasi Webhook...")
        info = await bot.get_webhook_info()
        print(f"• URL: {info.url}")
        print(f"• Pending updates: {info.pending_update_count}")
        print(f"• Has custom cert: {info.has_custom_certificate}")
        print(f"• Last error date: {info.last_error_date}")
        print(f"• Last error message: {info.last_error_message}")

    elif command == "delete":
        print("🗑 Menghapus Webhook...")
        success = await bot.delete_webhook(drop_pending_updates=True)
        if success:
            print("✅ Webhook berhasil dihapus.")
        else:
            print("❌ Gagal menghapus webhook.")


if __name__ == "__main__":
    asyncio.run(main())
