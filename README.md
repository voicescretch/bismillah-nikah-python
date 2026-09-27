# 💍 Bot Telegram Manajemen Tabungan Pasangan - "Bismillah Nikah"

Bot Telegram berbasis Python 3.10+ yang dirancang khusus untuk memfasilitasi pasangan dalam mengelola, mencatat pemasukan & pengeluaran, memantau saldo bersama, dan mengunduh rekap riwayat tabungan ke dalam format file Excel (.xlsx). Siap dideploy ke **Vercel Serverless Function** menggunakan Webhook dan database **PostgreSQL (Neon.tech)**.

---

## 📁 Struktur Direktori

```text
BismillahNikahBot/
├── api/
│   └── index.py            # Vercel Serverless Webhook Handler (FastAPI + ASGI)
├── bot/
│   ├── __init__.py
│   ├── config.py           # Konfigurasi & Muat Environment Variables
│   ├── database.py         # SQLAlchemy Async Engine, Models & Inisialisasi DB
│   ├── handlers.py         # Handler seluruh perintah Telegram & Callback Queries
│   └── utils.py            # Parser nominal, formatter Rupiah & Generator Excel
├── .env.example            # Template file variabel lingkungan
├── local_run.py            # Runner lokal menggunakan mode Long Polling
├── set_webhook.py          # Utilitas untuk set/delete webhook Telegram
├── requirements.txt        # Dependensi Python
├── vercel.json             # Konfigurasi routing Vercel Serverless
└── README.md               # Dokumentasi lengkap
```

---

## 🛠️ Tech Stack & Fitur

- **Language & Core Framework:** Python 3.10+, `python-telegram-bot` (v20+ Async), `FastAPI`
- **Database & ORM:** PostgreSQL (Neon.tech), `SQLAlchemy` (Asyncio dengan `asyncpg`)
- **Reporting Engine:** `pandas` & `openpyxl` (Export Excel via In-Memory `io.BytesIO`)
- **Deployment Platform:** Vercel (Serverless Function Webhook)

---

## 🗄️ Struktur Database (PostgreSQL)

1. **`users` (Data Pengguna)**
   - `telegram_id` (BigInteger, Primary Key)
   - `username` (String, nullable)
   - `full_name` (String)
   - `group_id` (Integer, ForeignKey ke `savings_groups.id`, nullable)
   - `created_at` (DateTime with timezone)

2. **`savings_groups` (Kelompok Tabungan Pasangan)**
   - `id` (Integer, Primary Key, Autoincrement)
   - `invite_code` (String(6), Unique, Nullable)
   - `code_expires_at` (DateTime with timezone, Nullable)
   - `created_at` (DateTime with timezone)

3. **`transactions` (Riwayat Transaksi Tabungan)**
   - `id` (Integer, Primary Key, Autoincrement)
   - `user_id` (BigInteger, ForeignKey ke `users.telegram_id`)
   - `group_id` (Integer, ForeignKey ke `savings_groups.id`)
   - `type` (String: `'PEMASUKAN'` / `'PENGELUARAN'`)
   - `amount` (BigInteger)
   - `description` (String, Nullable)
   - `created_at` (DateTime with timezone)

---

## 🤖 Daftar Perintah Bot

| Perintah | Deskripsi |
|---|---|
| `/start` | Memulai bot, melihat status akun, dan mendukung tautan Deep-Linking (`/start invite_CODE`) |
| `/help` | Menampilkan panduan lengkap seluruh perintah bot |
| `/profil` | Melihat profil pengguna dan status keterhubungan tabungan bersama pasangan |
| `/hubungkan` | Menghasilkan kode unik 6-karakter acak (berlaku 5 menit) dan tautan undangan instan |
| `/terima <kode>` | Menerima undangan dan menghubungkan akun ke kelompok tabungan pasangan (maks. 2 orang) |
| `/daftarhubungan` | Menampilkan daftar anggota kelompok tabungan saat ini |
| `/batalkanhubungan` | Mengeluarkan pasangan dari kelompok dengan konfirmasi Inline Keyboard |
| `/keluarhubungan` | Keluar dari kelompok tabungan saat ini dengan konfirmasi Inline Keyboard |
| `/menabung <nominal> [ket]` | Mencatat uang masuk tabungan (Contoh: `/menabung 500.000 Gaji`) |
| `/penarikan <nominal> [ket]` | Mencatat uang keluar (Contoh: `/penarikan 150000 DP Gedung`) |
| `/total` | Menampilkan ringkasan saldo masing-masing anggota & total saldo gabungan kelompok |
| `/ringkasan` | Menampilkan rincian Total Pemasukan, Total Pengeluaran, Net Saldo, dan total grup |
| `/riwayat` | Mengirimkan file Excel (.xlsx) rapi dengan kalkulasi total dan filter (`pribadi` / `@username`) |

---

## 🚀 Panduan Instalasi & Menjalankan Lokal

### 1. Clone & Setup Virtual Environment
```bash
git clone <URL_REPOSITORY>
cd BismillahNikahBot

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Konfigurasi File `.env`
Salin file `.env.example` menjadi `.env`:
```bash
cp .env.example .env
```
Isi konfigurasi berikut:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
BOT_USERNAME=BismillahNikah_bot
DATABASE_URL=postgresql+asyncpg://username:password@ep-sample-12345.us-east-2.aws.neon.tech/neondb?ssl=require
WEBHOOK_SECRET=random_secret_token_kamu
```

### 3. Jalankan Pengujian Lokal (Mode Long Polling)
```bash
python local_run.py
```
> Tabel database akan otomatis dibuat saat aplikasi dijalankan pertama kali.

---

## ☁️ Panduan Deploy ke Vercel (Serverless Webhook)

### Langkah 1: Push ke GitHub / GitLab
Pastikan seluruh file proyek telah di-commit dan di-push ke repository GitHub milikmu.

### Langkah 2: Hubungkan Repository ke Vercel
1. Masuk ke dashboard [Vercel](https://vercel.com).
2. Klik **Add New...** -> **Project**, lalu pilih repository `BismillahNikahBot`.
3. Pada bagian **Environment Variables**, tambahkan:
   - `TELEGRAM_BOT_TOKEN`
   - `BOT_USERNAME`
   - `DATABASE_URL` (Gunakan URL PostgreSQL dari Neon.tech)
   - `WEBHOOK_SECRET`
4. Klik **Deploy**.

### Langkah 3: Daftarkan Webhook ke Telegram
Setelah deployment di Vercel selesai, kamu akan mendapatkan domain (contoh: `https://bismillah-nikah.vercel.app`).

Jalankan script `set_webhook.py` di komputer lokalmu:
```bash
python set_webhook.py set https://bismillah-nikah.vercel.app/api
```

Untuk mengecek status webhook:
```bash
python set_webhook.py info
```

🎉 **Selesai!** Bot "Bismillah Nikah" kini sudah aktif 24/7 di serverless Vercel!
