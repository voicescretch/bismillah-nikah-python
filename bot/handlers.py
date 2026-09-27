import html
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from bot.config import BOT_USERNAME, TELEGRAM_BOT_TOKEN
from bot.database import SavingsGroup, Transaction, User, get_session
from bot.utils import (
    format_rupiah,
    generate_excel_report,
    generate_invite_code,
    parse_nominal_and_description,
)

logger = logging.getLogger(__name__)


# ==========================================
# HELPER FUNCTIONS
# ==========================================

async def get_or_create_user(session, telegram_user) -> User:
    """Mengambil atau membuat data user di database."""
    stmt = select(User).options(selectinload(User.group).selectinload(SavingsGroup.members)).where(
        User.telegram_id == telegram_user.id
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    full_name = telegram_user.full_name or "Pengguna"
    username = telegram_user.username

    if not user:
        user = User(
            telegram_id=telegram_user.id,
            username=username,
            full_name=full_name,
        )
        session.add(user)
        await session.flush()
    else:
        # Perbarui nama atau username jika ada perubahan di Telegram
        if user.full_name != full_name or user.username != username:
            user.full_name = full_name
            user.username = username
            await session.flush()

    return user


async def ensure_group_for_user(session, user: User) -> SavingsGroup:
    """Memastikan pengguna memiliki kelompok tabungan."""
    if user.group_id and user.group:
        return user.group
    
    # Cari jika ada grup
    if user.group_id:
        stmt = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == user.group_id)
        res = await session.execute(stmt)
        group = res.scalar_one_or_none()
        if group:
            return group

    # Buat grup baru
    new_group = SavingsGroup()
    session.add(new_group)
    await session.flush()

    user.group_id = new_group.id
    await session.flush()
    return new_group


# ==========================================
# COMMAND HANDLERS
# ==========================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk /start.
    Mendukung deep-linking: /start invite_<CODE>
    """
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    args = context.args or []

    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        # Cek apakah ada parameter deep linking (contoh: invite_ABC123)
        if args and args[0].startswith("invite_"):
            code = args[0].replace("invite_", "").strip().upper()
            await process_accept_code(update, context, session, user, code)
            return

        status_grup = "Belum Terhubung dengan Pasangan ❌"
        partner_info = ""

        if user.group_id:
            stmt = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == user.group_id)
            res = await session.execute(stmt)
            group = res.scalar_one_or_none()
            if group:
                partners = [m for m in group.members if m.telegram_id != user.telegram_id]
                if partners:
                    partner = partners[0]
                    p_name = f"@{partner.username}" if partner.username else partner.full_name
                    status_grup = f"Terhubung dengan <b>{html.escape(p_name)}</b> 💍"
                else:
                    status_grup = "Kelompok Mandiri (Belum ada pasangan yang bergabung)"

        text = (
            f"💍 <b>Selamat Datang di Bot Tabungan 'Bismillah Nikah'!</b> 💍\n\n"
            f"Halo, <b>{html.escape(user.full_name)}</b>!\n"
            f"Bot ini dirancang khusus untuk membantu pasangan mengelola, mencatat, dan memantau tabungan bersama menuju hari bahagia.\n\n"
            f"📌 <b>Status Tabungan:</b> {status_grup}\n\n"
            f"💡 <b>Langkah Awal:</b>\n"
            f"1. Gunakan /hubungkan untuk mengundang pasangan kamu.\n"
            f"2. Gunakan /terima <code>&lt;kode&gt;</code> jika kamu memiliki kode undangan dari pasangan.\n"
            f"3. Ketik /help untuk melihat seluruh panduan perintah."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /help - Menampilkan panduan lengkap."""
    if not update.message:
        return

    help_text = (
        "📖 <b>PANDUAN PERINTAH BOT 'BISMILLAH NIKAH'</b> 💍\n\n"
        "🔗 <b>Koneksi & Pasangan:</b>\n"
        "• /hubungkan - Buat kode & link undangan untuk pasangan (berlaku 5 mnt)\n"
        "• /terima <code>&lt;kode&gt;</code> - Masuk ke kelompok tabungan pasangan\n"
        "• /daftarhubungan - Lihat anggota kelompok tabungan saat ini\n"
        "• /batalkanhubungan <code>&lt;@username&gt;</code> - Keluarkan pasangan dari grup\n"
        "• /keluarhubungan - Keluar dari kelompok tabungan saat ini\n\n"
        "💰 <b>Transaksi & Catatan:</b>\n"
        "• /menabung <code>&lt;nominal&gt; [keterangan]</code> - Catat uang masuk\n"
        "  <i>Contoh: <code>/menabung 500.000 Gaji bulanan</code></i>\n"
        "• /penarikan <code>&lt;nominal&gt; [keterangan]</code> - Catat uang keluar\n"
        "  <i>Contoh: <code>/penarikan 150000 DP Gedung</code></i>\n\n"
        "📊 <b>Laporan & Informasi:</b>\n"
        "• /total - Ringkasan saldo masing-masing & total bersama\n"
        "• /ringkasan - Detail rincian pemasukan, pengeluaran & sisa saldo\n"
        "• /riwayat - Unduh rekap lengkap file Excel (.xlsx)\n"
        "  <i>Opsi: <code>/riwayat pribadi</code> atau <code>/riwayat @username</code></i>\n"
        "• /profil - Lihat informasi akun dan kelompok tabungan\n"
        "• /help - Tampilkan pesan bantuan ini"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def profil_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /profil - Menampilkan profil pengguna."""
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        status_text = "Belum terhubung ke kelompok tabungan bersama."
        partner_text = "-"

        if user.group_id:
            stmt = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == user.group_id)
            res = await session.execute(stmt)
            group = res.scalar_one_or_none()
            if group:
                partners = [m for m in group.members if m.telegram_id != user.telegram_id]
                if partners:
                    partner = partners[0]
                    p_uname = f"@{partner.username}" if partner.username else "(tidak ada username)"
                    status_text = "✅ Terhubung Bersama Pasangan"
                    partner_text = f"{html.escape(partner.full_name)} ({p_uname})"
                else:
                    status_text = "Tabungan Mandiri (Belum ada pasangan terhubung)"

        uname_str = f"@{user.username}" if user.username else "<i>(Belum diatur)</i>"
        created_str = user.created_at.strftime("%d-%m-%Y %H:%M") if user.created_at else "-"

        text = (
            "👤 <b>PROFIL PENGGUNA</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Nama:</b> {html.escape(user.full_name)}\n"
            f"• <b>Username:</b> {uname_str}\n"
            f"• <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
            f"• <b>Terdaftar Sejak:</b> {created_str}\n\n"
            f"💍 <b>Status Hubungan Tabungan:</b>\n"
            f"• <b>Status:</b> {status_text}\n"
            f"• <b>Pasangan:</b> {partner_text}\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def hubungkan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /hubungkan - Membuat kode undangan 6 karakter yang berlaku 5 menit."""
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    bot_uname = BOT_USERNAME or (context.bot.username if context.bot else "BismillahNikah_bot")

    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)
        group = await ensure_group_for_user(session, user)

        # Cek jika grup sudah memiliki 2 anggota
        stmt = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == group.id)
        res = await session.execute(stmt)
        group_with_members = res.scalar_one_or_none()

        if group_with_members and len(group_with_members.members) >= 2:
            partner = [m for m in group_with_members.members if m.telegram_id != user.telegram_id][0]
            await update.message.reply_text(
                f"⚠️ Kelompok tabunganmu sudah penuh (terhubung dengan <b>{html.escape(partner.full_name)}</b>).\n"
                f"Gunakan /batalkanhubungan atau /keluarhubungan jika ingin mengatur ulang pasangan.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Generate kode undangan acak & waktu kedaluwarsa 5 menit
        invite_code = generate_invite_code(6)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        group.invite_code = invite_code
        group.code_expires_at = expires_at
        await session.flush()

        invite_link = f"https://t.me/{bot_uname}?start=invite_{invite_code}"

        msg = (
            "🔐 <b>KODE UNDANGAN TABUNGAN PASANGAN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Kode Undangan: <code>{invite_code}</code>\n"
            f"⏱ <i>Berlaku selama 5 menit.</i>\n\n"
            f"Kirimkan link tautan instan ini kepada calon pasanganmu:\n"
            f"👉 {invite_link}\n\n"
            f"Atau minta pasanganmu mengirimkan perintah berikut ke bot:\n"
            f"<code>/terima {invite_code}</code>\n\n"
            "⚠️ <b>Peringatan Keamanan:</b>\n"
            "Jangan bagikan kode ini kepada siapa pun selain calon pasanganmu!",
        )
        await update.message.reply_text("".join(msg), parse_mode=ParseMode.HTML)


async def terima_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /terima <kode>."""
    if not update.effective_user or not update.message:
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "⚠️ Format salah. Gunakan: <code>/terima &lt;KODE_6_KARAKTER&gt;</code>\n"
            "Contoh: <code>/terima ABC123</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    code = args[0].strip().upper()
    tg_user = update.effective_user

    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)
        await process_accept_code(update, context, session, user, code)


async def process_accept_code(update: Update, context: ContextTypes.DEFAULT_TYPE, session, user: User, code: str):
    """Memproses logika penerimaan kode undangan."""
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if not message:
        return

    # Cari kelompok tabungan dengan invite_code tersebut
    now = datetime.now(timezone.utc)
    stmt = (
        select(SavingsGroup)
        .options(selectinload(SavingsGroup.members))
        .where(SavingsGroup.invite_code == code)
    )
    res = await session.execute(stmt)
    target_group = res.scalar_one_or_none()

    if not target_group:
        await message.reply_text(
            "❌ <b>Kode Undangan Tidak Valid!</b>\n"
            "Pastikan kode yang dimasukkan sudah benar atau minta pasanganmu membuat kode baru dengan /hubungkan.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Cek kedaluwarsa
    if target_group.code_expires_at and target_group.code_expires_at < now:
        await message.reply_text(
            "⏳ <b>Kode Undangan Sudah Kadaluarsa!</b>\n"
            "Kode hanya berlaku 5 menit. Silakan minta pasanganmu menjalankan /hubungkan kembali.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Cek apakah user mencoba menghubungkan ke kodenya sendiri
    existing_owner = target_group.members[0] if target_group.members else None
    if existing_owner and existing_owner.telegram_id == user.telegram_id:
        await message.reply_text(
            "😅 Kamu tidak bisa menerima kode undangan milikmu sendiri.\n"
            "Kirimkan kode atau tautan tersebut kepada pasanganmu!",
            parse_mode=ParseMode.HTML,
        )
        return

    # Cek jumlah anggota di target group
    if len(target_group.members) >= 2:
        await message.reply_text(
            "❌ Kelompok tabungan tersebut sudah penuh (maksimal 2 pasangan).",
            parse_mode=ParseMode.HTML,
        )
        return

    # Cek jika user saat ini sudah tergabung di grup lain dengan anggota lain
    if user.group_id and user.group_id != target_group.id:
        stmt_curr = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == user.group_id)
        res_curr = await session.execute(stmt_curr)
        curr_group = res_curr.scalar_one_or_none()
        if curr_group and len(curr_group.members) > 1:
            await message.reply_text(
                "⚠️ Kamu sudah terhubung dengan kelompok tabungan lain.\n"
                "Silakan keluar terlebih dahulu menggunakan /keluarhubungan sebelum bergabung ke kelompok baru.",
                parse_mode=ParseMode.HTML,
            )
            return

    # Hubungkan user ke target_group
    user.group_id = target_group.id
    target_group.invite_code = None  # Reset kode setelah berhasil dipakai
    target_group.code_expires_at = None
    await session.flush()

    partner_name = existing_owner.full_name if existing_owner else "Pasanganmu"

    await message.reply_text(
        f"🎉 <b>Alhamdulillah, Berhasil Terhubung!</b> 💍\n\n"
        f"Kamu sekarang telah terhubung dalam kelompok tabungan bersama <b>{html.escape(partner_name)}</b>.\n\n"
        f"Mulai catat tabungan pernikahan kalian dengan perintah:\n"
        f"• /menabung <code>&lt;nominal&gt; [keterangan]</code>\n"
        f"• /total untuk memantau tabungan bersama.",
        parse_mode=ParseMode.HTML,
    )

    # Kirim notifikasi ke pasangan jika ada
    if existing_owner:
        try:
            await context.bot.send_message(
                chat_id=existing_owner.telegram_id,
                text=(
                    f"🎉 <b>Kabar Gembira!</b>\n\n"
                    f"<b>{html.escape(user.full_name)}</b> telah bergabung ke dalam kelompok tabungan bersama kamu! 💍\n"
                    f"Semoga tabungan kalian berkah menuju pernikahan yang sakinah, mawaddah, warahmah."
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("Gagal mengirim notifikasi ke pemilik grup: %s", e)


async def daftarhubungan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /daftarhubungan - Menampilkan daftar anggota kelompok tabungan."""
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        if not user.group_id:
            await update.message.reply_text(
                "ℹ️ Kamu belum memiliki kelompok tabungan.\n"
                "Gunakan /hubungkan untuk membuat kode undangan bagi pasanganmu.",
                parse_mode=ParseMode.HTML,
            )
            return

        stmt = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == user.group_id)
        res = await session.execute(stmt)
        group = res.scalar_one_or_none()

        if not group or not group.members:
            await update.message.reply_text("ℹ️ Kelompok tabungan tidak ditemukan.")
            return

        member_lines = []
        for idx, m in enumerate(group.members, start=1):
            uname = f"(@{m.username})" if m.username else ""
            is_you = " <i>(Kamu)</i>" if m.telegram_id == user.telegram_id else ""
            joined_at = m.created_at.strftime("%d-%m-%Y") if m.created_at else "-"
            member_lines.append(f"{idx}. <b>{html.escape(m.full_name)}</b> {uname}{is_you}\n   └ Terdaftar: {joined_at}")

        text = (
            "👥 <b>DAFTAR ANGGOTA TABUNGAN BERSAMA</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(member_lines)
            + "\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Total Anggota: {len(group.members)} / 2 orang"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def batalkanhubungan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk /batalkanhubungan <username/opsional>.
    Mengirim Inline Keyboard konfirmasi untuk mengeluarkan pasangan.
    """
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        if not user.group_id:
            await update.message.reply_text("⚠️ Kamu belum terhubung ke kelompok tabungan manapun.")
            return

        stmt = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == user.group_id)
        res = await session.execute(stmt)
        group = res.scalar_one_or_none()

        if not group:
            await update.message.reply_text("⚠️ Kelompok tabungan tidak ditemukan.")
            return

        partners = [m for m in group.members if m.telegram_id != user.telegram_id]
        if not partners:
            await update.message.reply_text("⚠️ Tidak ada pasangan di kelompok tabunganmu saat ini.")
            return

        target_partner = None
        args = context.args or []

        if args:
            raw_target = args[0].strip().lstrip("@").lower()
            for p in partners:
                if (p.username and p.username.lower() == raw_target) or str(p.telegram_id) == raw_target:
                    target_partner = p
                    break
            if not target_partner:
                await update.message.reply_text(
                    f"❌ Pasangan dengan username/ID @{args[0]} tidak ditemukan di kelompokmu.",
                    parse_mode=ParseMode.HTML,
                )
                return
        else:
            target_partner = partners[0]

        keyboard = [
            [
                InlineKeyboardButton("✅ Ya, Keluarkan", callback_data=f"kick_{target_partner.telegram_id}"),
                InlineKeyboardButton("❌ Batal", callback_data="cancel_action"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        p_name = target_partner.full_name + (f" (@{target_partner.username})" if target_partner.username else "")
        msg = (
            f"⚠️ <b>KONFIRMASI PENGELUARAN ANGGOTA</b>\n\n"
            f"Apakah kamu yakin ingin mengeluarkan <b>{html.escape(p_name)}</b> dari kelompok tabungan bersama?\n\n"
            f"<i>Catatan: Riwayat transaksi yang telah dicatat tetap tersimpan di database.</i>"
        )
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def keluarhubungan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk /keluarhubungan.
    Mengirim Inline Keyboard konfirmasi untuk keluar dari kelompok tabungan.
    """
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        if not user.group_id:
            await update.message.reply_text("⚠️ Kamu saat ini tidak terhubung ke kelompok tabungan manapun.")
            return

        keyboard = [
            [
                InlineKeyboardButton("✅ Ya, Keluar", callback_data=f"leave_{user.telegram_id}"),
                InlineKeyboardButton("❌ Batal", callback_data="cancel_action"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        msg = (
            "⚠️ <b>KONFIRMASI KELUAR DARI KELOMPOK TABUNGAN</b>\n\n"
            "Apakah kamu yakin ingin keluar dari kelompok tabungan bersama saat ini?\n\n"
            "<i>Catatan: Catatan riwayat tabungan tidak akan terhapus.</i>"
        )
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menangani tombol Inline Keyboard konfirmasi."""
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return

    await query.answer()
    data = query.data
    tg_user = update.effective_user

    if data == "cancel_action":
        await query.edit_message_text("❌ Tindakan dibatalkan.")
        return

    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        if data.startswith("kick_"):
            target_id_str = data.replace("kick_", "").strip()
            if not target_id_str.isdigit():
                await query.edit_message_text("❌ Data tidak valid.")
                return

            target_id = int(target_id_str)
            stmt = select(User).where(User.telegram_id == target_id)
            res = await session.execute(stmt)
            target_user = res.scalar_one_or_none()

            if not target_user or target_user.group_id != user.group_id:
                await query.edit_message_text("⚠️ Anggota tersebut sudah tidak berada dalam kelompokmu.")
                return

            # Lepaskan anggota dari kelompok
            target_user.group_id = None
            await session.flush()

            await query.edit_message_text(
                f"✅ <b>{html.escape(target_user.full_name)}</b> berhasil dikeluarkan dari kelompok tabungan.",
                parse_mode=ParseMode.HTML,
            )

            try:
                await context.bot.send_message(
                    chat_id=target_user.telegram_id,
                    text="ℹ️ Kamu telah dikeluarkan dari kelompok tabungan bersama.",
                )
            except Exception as e:
                logger.warning("Gagal mengirim notifikasi ke user yang dikeluarkan: %s", e)

        elif data.startswith("leave_"):
            user_id_str = data.replace("leave_", "").strip()
            if str(user.telegram_id) != user_id_str:
                await query.edit_message_text("❌ Tindakan tidak diizinkan.")
                return

            old_group_id = user.group_id
            user.group_id = None
            await session.flush()

            await query.edit_message_text(
                "✅ Kamu telah berhasil keluar dari kelompok tabungan bersama.",
                parse_mode=ParseMode.HTML,
            )

            # Beritahu sisa anggota di grup lama jika ada
            if old_group_id:
                stmt_remain = select(User).where(User.group_id == old_group_id)
                res_remain = await session.execute(stmt_remain)
                remaining_members = res_remain.scalars().all()
                for member in remaining_members:
                    try:
                        await context.bot.send_message(
                            chat_id=member.telegram_id,
                            text=f"ℹ️ <b>{html.escape(user.full_name)}</b> telah keluar dari kelompok tabungan.",
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception as e:
                        logger.warning("Gagal mengirim notifikasi keluar ke partner: %s", e)


async def menabung_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /menabung <nominal> [keterangan]."""
    if not update.effective_user or not update.message:
        return

    args = context.args or []
    amount, desc = parse_nominal_and_description(args)

    if not amount:
        await update.message.reply_text(
            "⚠️ <b>Format Perintah Salah!</b>\n\n"
            "Gunakan format: <code>/menabung &lt;nominal&gt; [keterangan]</code>\n\n"
            "💡 <i>Contoh:</i>\n"
            "• <code>/menabung 100000</code>\n"
            "• <code>/menabung 500.000 Gaji Pokok</code>\n"
            "• <code>/menabung Rp 1.500.000 Bonus Project</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    tg_user = update.effective_user
    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)
        group = await ensure_group_for_user(session, user)

        # Simpan transaksi
        tx = Transaction(
            user_id=user.telegram_id,
            group_id=group.id,
            type="PEMASUKAN",
            amount=amount,
            description=desc,
        )
        session.add(tx)
        await session.flush()

        # Hitung saldo total terkini grup
        stmt_in = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(Transaction.group_id == group.id, Transaction.type == "PEMASUKAN")
        )
        stmt_out = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(Transaction.group_id == group.id, Transaction.type == "PENGELUARAN")
        )
        tot_in = (await session.execute(stmt_in)).scalar()
        tot_out = (await session.execute(stmt_out)).scalar()
        total_saldo = tot_in - tot_out

        desc_text = f"• Keterangan: <i>{html.escape(desc)}</i>\n" if desc else ""
        msg = (
            "✅ <b>MENABUNG BERHASIL DICATAT!</b> 💵\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Anggota: <b>{html.escape(user.full_name)}</b>\n"
            f"• Tipe: 🟢 PEMASUKAN\n"
            f"• Nominal: <b>{format_rupiah(amount)}</b>\n"
            f"{desc_text}"
            f"• Tanggal: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Total Saldo Tabungan Bersama:</b> {format_rupiah(total_saldo)}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def penarikan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /penarikan <nominal> [keterangan]."""
    if not update.effective_user or not update.message:
        return

    args = context.args or []
    amount, desc = parse_nominal_and_description(args)

    if not amount:
        await update.message.reply_text(
            "⚠️ <b>Format Perintah Salah!</b>\n\n"
            "Gunakan format: <code>/penarikan &lt;nominal&gt; [keterangan]</code>\n\n"
            "💡 <i>Contoh:</i>\n"
            "• <code>/penarikan 50000</code>\n"
            "• <code>/penarikan 250.000 DP Souvenir</code>\n"
            "• <code>/penarikan Rp 1.000.000 DP Catering</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    tg_user = update.effective_user
    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)
        group = await ensure_group_for_user(session, user)

        # Simpan transaksi penarikan
        tx = Transaction(
            user_id=user.telegram_id,
            group_id=group.id,
            type="PENGELUARAN",
            amount=amount,
            description=desc,
        )
        session.add(tx)
        await session.flush()

        # Hitung saldo total terkini grup
        stmt_in = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(Transaction.group_id == group.id, Transaction.type == "PEMASUKAN")
        )
        stmt_out = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(Transaction.group_id == group.id, Transaction.type == "PENGELUARAN")
        )
        tot_in = (await session.execute(stmt_in)).scalar()
        tot_out = (await session.execute(stmt_out)).scalar()
        total_saldo = tot_in - tot_out

        desc_text = f"• Keterangan: <i>{html.escape(desc)}</i>\n" if desc else ""
        msg = (
            "💸 <b>PENARIKAN BERHASIL DICATAT!</b> 📤\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Anggota: <b>{html.escape(user.full_name)}</b>\n"
            f"• Tipe: 🔴 PENGELUARAN\n"
            f"• Nominal: <b>{format_rupiah(amount)}</b>\n"
            f"{desc_text}"
            f"• Tanggal: {datetime.now().strftime('%d-%m-%Y %H:%M')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Sisa Saldo Tabungan Bersama:</b> {format_rupiah(total_saldo)}"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def total_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk /total - Menampilkan ringkasan sisa saldo masing-masing & saldo gabungan."""
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        if not user.group_id:
            await update.message.reply_text(
                "ℹ️ Belum ada tabungan yang tercatat. Mulai menabung dengan /menabung atau hubungkan pasangan dengan /hubungkan."
            )
            return

        stmt_group = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == user.group_id)
        res_group = await session.execute(stmt_group)
        group = res_group.scalar_one_or_none()

        if not group:
            await update.message.reply_text("ℹ️ Kelompok tabungan tidak ditemukan.")
            return

        # Ambil seluruh transaksi dalam grup
        stmt_tx = select(Transaction).options(selectinload(Transaction.user)).where(Transaction.group_id == group.id)
        res_tx = await session.execute(stmt_tx)
        transactions = res_tx.scalars().all()

        member_balances = {m.telegram_id: {"name": m.full_name, "username": m.username, "balance": 0} for m in group.members}

        total_pemasukan = 0
        total_pengeluaran = 0

        for tx in transactions:
            if tx.user_id not in member_balances:
                # Jika ada user yang pernah transaksi tapi sudah keluar dari grup
                u_name = tx.user.full_name if tx.user else f"ID {tx.user_id}"
                u_uname = tx.user.username if tx.user else None
                member_balances[tx.user_id] = {"name": u_name, "username": u_uname, "balance": 0}

            if tx.type == "PEMASUKAN":
                member_balances[tx.user_id]["balance"] += tx.amount
                total_pemasukan += tx.amount
            elif tx.type == "PENGELUARAN":
                member_balances[tx.user_id]["balance"] -= tx.amount
                total_pengeluaran += tx.amount

        total_gabungan = total_pemasukan - total_pengeluaran

        member_details = []
        for uid, data in member_balances.items():
            uname_str = f" (@{data['username']})" if data["username"] else ""
            is_you = " <i>(Kamu)</i>" if uid == user.telegram_id else ""
            member_details.append(
                f"👤 <b>{html.escape(data['name'])}</b>{uname_str}{is_you}\n"
                f"   └ Saldo: <b>{format_rupiah(data['balance'])}</b>"
            )

        text = (
            "📊 <b>TOTAL SALDO TABUNGAN PASANGAN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n\n".join(member_details)
            + "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💍 <b>TOTAL SALDO GABUNGAN:</b>\n"
            f"👉 <b>{format_rupiah(total_gabungan)}</b>"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def ringkasan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk /ringkasan - Menampilkan rincian Total Pemasukan, Total Pengeluaran,
    dan Net Saldo per anggota & total grup.
    """
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        if not user.group_id:
            await update.message.reply_text("ℹ️ Belum ada catatan tabungan. Gunakan /menabung untuk mulai mencatat.")
            return

        stmt_group = select(SavingsGroup).options(selectinload(SavingsGroup.members)).where(SavingsGroup.id == user.group_id)
        res_group = await session.execute(stmt_group)
        group = res_group.scalar_one_or_none()

        if not group:
            await update.message.reply_text("ℹ️ Kelompok tabungan tidak ditemukan.")
            return

        stmt_tx = select(Transaction).options(selectinload(Transaction.user)).where(Transaction.group_id == group.id)
        res_tx = await session.execute(stmt_tx)
        transactions = res_tx.scalars().all()

        member_stats = {
            m.telegram_id: {
                "name": m.full_name,
                "username": m.username,
                "in": 0,
                "out": 0,
                "count": 0,
            }
            for m in group.members
        }

        group_total_in = 0
        group_total_out = 0

        for tx in transactions:
            if tx.user_id not in member_stats:
                u_name = tx.user.full_name if tx.user else f"ID {tx.user_id}"
                u_uname = tx.user.username if tx.user else None
                member_stats[tx.user_id] = {"name": u_name, "username": u_uname, "in": 0, "out": 0, "count": 0}

            member_stats[tx.user_id]["count"] += 1
            if tx.type == "PEMASUKAN":
                member_stats[tx.user_id]["in"] += tx.amount
                group_total_in += tx.amount
            elif tx.type == "PENGELUARAN":
                member_stats[tx.user_id]["out"] += tx.amount
                group_total_out += tx.amount

        group_net_saldo = group_total_in - group_total_out

        details = []
        for uid, data in member_stats.items():
            uname_str = f" (@{data['username']})" if data["username"] else ""
            is_you = " <i>(Kamu)</i>" if uid == user.telegram_id else ""
            net = data["in"] - data["out"]
            details.append(
                f"👤 <b>{html.escape(data['name'])}</b>{uname_str}{is_you}\n"
                f"   ├ Total Menabung: 🟢 {format_rupiah(data['in'])}\n"
                f"   ├ Total Penarikan: 🔴 {format_rupiah(data['out'])}\n"
                f"   ├ Net Saldo: <b>{format_rupiah(net)}</b>\n"
                f"   └ Jumlah Transaksi: {data['count']}x"
            )

        text = (
            "📑 <b>RINGKASAN KEUANGAN TABUNGAN PASANGAN</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            + "\n\n".join(details)
            + "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💍 <b>TOTAL KELOMPOK TABUNGAN:</b>\n"
            f"• Total Pemasukan: 🟢 <b>{format_rupiah(group_total_in)}</b>\n"
            f"• Total Pengeluaran: 🔴 <b>{format_rupiah(group_total_out)}</b>\n"
            f"• Sisa Saldo Bersama: 💰 <b>{format_rupiah(group_net_saldo)}</b>\n"
            f"• Total Transaksi: {len(transactions)} transaksi"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def riwayat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler untuk /riwayat [pribadi | @username].
    Mengirimkan file Excel (.xlsx) dengan kalkulasi lengkap di baris bawah.
    """
    if not update.effective_user or not update.message:
        return

    tg_user = update.effective_user
    args = context.args or []

    async with get_session() as session:
        user = await get_or_create_user(session, tg_user)

        if not user.group_id:
            await update.message.reply_text("ℹ️ Belum ada riwayat transaksi tabungan.")
            return

        # Query transaksi
        stmt = (
            select(Transaction)
            .options(selectinload(Transaction.user))
            .where(Transaction.group_id == user.group_id)
            .order_by(Transaction.created_at.asc())
        )
        res = await session.execute(stmt)
        transactions = list(res.scalars().all())

        if not transactions:
            await update.message.reply_text("ℹ️ Belum ada transaksi yang tercatat dalam kelompok ini.")
            return

        filter_type = "seluruh"
        target_user_id = None
        target_label = "Seluruh Grup"

        if args:
            filter_arg = args[0].strip().lower()
            if filter_arg == "pribadi":
                filter_type = "pribadi"
                target_user_id = user.telegram_id
                target_label = f"Pribadi - {user.full_name}"
            else:
                # Filter by username or telegram id
                raw_uname = filter_arg.lstrip("@")
                stmt_u = select(User).where(func.lower(User.username) == raw_uname)
                res_u = await session.execute(stmt_u)
                found_user = res_u.scalar_one_or_none()

                if found_user:
                    target_user_id = found_user.telegram_id
                    target_label = f"Anggota @{found_user.username}"
                else:
                    await update.message.reply_text(
                        f"⚠️ Pengguna dengan username @{raw_uname} tidak ditemukan.\n"
                        f"Menampilkan riwayat untuk seluruh grup.",
                        parse_mode=ParseMode.HTML,
                    )

        if target_user_id:
            filtered_tx = [tx for tx in transactions if tx.user_id == target_user_id]
            if not filtered_tx:
                await update.message.reply_text(f"ℹ️ Belum ada catatan transaksi untuk {target_label}.")
                return
            transactions = filtered_tx

        # Generate file Excel menggunakan BytesIO
        excel_buffer = generate_excel_report(transactions, title_suffix=target_label)
        filename = f"Riwayat_Tabungan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        # Hitung statistik singkat untuk caption
        tot_in = sum(tx.amount for tx in transactions if tx.type == "PEMASUKAN")
        tot_out = sum(tx.amount for tx in transactions if tx.type == "PENGELUARAN")
        saldo = tot_in - tot_out

        caption = (
            f"📊 <b>Laporan Riwayat Tabungan</b> ({target_label})\n"
            f"• Total Pemasukan: 🟢 {format_rupiah(tot_in)}\n"
            f"• Total Pengeluaran: 🔴 {format_rupiah(tot_out)}\n"
            f"• Sisa Saldo: 💰 <b>{format_rupiah(saldo)}</b>\n"
            f"• Jumlah Transaksi: {len(transactions)} baris\n\n"
            f"<i>File Excel (.xlsx) terlampir di atas.</i>"
        )

        await update.message.reply_document(
            document=excel_buffer,
            filename=filename,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler untuk logging."""
    logger.error("Exception saat memproses update:", exc_info=context.error)


def setup_application() -> Application:
    """Membangun dan mendaftarkan seluruh handler ke Application python-telegram-bot."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Daftarkan Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profil", profil_command))
    app.add_handler(CommandHandler("hubungkan", hubungkan_command))
    app.add_handler(CommandHandler("terima", terima_command))
    app.add_handler(CommandHandler("daftarhubungan", daftarhubungan_command))
    app.add_handler(CommandHandler("batalkanhubungan", batalkanhubungan_command))
    app.add_handler(CommandHandler("keluarhubungan", keluarhubungan_command))
    app.add_handler(CommandHandler("menabung", menabung_command))
    app.add_handler(CommandHandler("penarikan", penarikan_command))
    app.add_handler(CommandHandler("total", total_command))
    app.add_handler(CommandHandler("ringkasan", ringkasan_command))
    app.add_handler(CommandHandler("riwayat", riwayat_command))

    # Daftarkan Callback Query Handlers
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # Daftarkan Error Handler
    app.add_error_handler(error_handler)

    return app
