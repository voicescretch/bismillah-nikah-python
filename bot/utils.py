import io
import re
import secrets
import string
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def generate_invite_code(length: int = 6) -> str:
    """Menghasilkan kode unik acak alfanumerik huruf besar & angka."""
    chars = string.ascii_uppercase + string.digits
    # Hilangkan karakter ambigu seperti O dan 0, I dan 1 jika diinginkan, atau gunakan standar alfanumerik
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(chars) for _ in range(length))


def format_rupiah(amount: int) -> str:
    """Format integer nominal ke format mata uang Rupiah (contoh: Rp 150.000)."""
    return f"Rp {amount:,.0f}".replace(",", ".")


def parse_nominal_and_description(args: List[str]) -> Tuple[Optional[int], Optional[str]]:
    """
    Mem-parsing argumen perintah nominal dan keterangan opsional.
    Contoh input:
    - ["100000", "Beli", "cincin"] -> (100000, "Beli cincin")
    - ["Rp", "150.000", "Uang", "gedung"] -> (150000, "Uang gedung")
    - ["Rp.150.000"] -> (150000, None)
    - ["100.000"] -> (100000, None)
    """
    if not args:
        return None, None

    full_text = " ".join(args).strip()

    # Cari pola angka / nominal di awal teks
    # Mendukung awalan 'rp', 'rp.', 'idr', spasi, titik, koma
    pattern = r"^(?:rp\.?|idr)?\s*([0-9]{1,3}(?:[.,\s][0-9]{3})*|[0-9]+)\s*(.*)$"
    match = re.match(pattern, full_text, re.IGNORECASE)

    if not match:
        # Coba cara kedua jika pola tidak cocok
        raw_token = args[0].strip()
        cleaned_token = re.sub(r"[^\d]", "", raw_token)
        if cleaned_token.isdigit():
            amount = int(cleaned_token)
            desc = " ".join(args[1:]).strip() if len(args) > 1 else None
            return (amount if amount > 0 else None), (desc if desc else None)
        return None, None

    nominal_str, desc_str = match.groups()
    cleaned_num = re.sub(r"[^\d]", "", nominal_str)

    if not cleaned_num or not cleaned_num.isdigit():
        return None, None

    amount = int(cleaned_num)
    if amount <= 0:
        return None, None

    description = desc_str.strip() if desc_str and desc_str.strip() else None
    return amount, description


def generate_excel_report(
    transactions: list,
    title_suffix: str = "Seluruh Grup"
) -> io.BytesIO:
    """
    Meng-generate file Excel (.xlsx) rapi dengan Pandas dan Openpyxl.
    Kolom: Tanggal, Anggota, Tipe, Nominal, Keterangan.
    Baris bawah: Total Pemasukan, Total Pengeluaran, Sisa Saldo.
    """
    rows = []
    total_pemasukan = 0
    total_pengeluaran = 0

    for tx in transactions:
        user_name = tx.user.full_name if tx.user else "Unknown"
        if tx.user and tx.user.username:
            user_name += f" (@{tx.user.username})"

        # Format tanggal (WIB / format lokal)
        dt_str = tx.created_at.strftime("%d/%m/%Y %H:%M") if tx.created_at else "-"

        if tx.type == "PEMASUKAN":
            total_pemasukan += tx.amount
        elif tx.type == "PENGELUARAN":
            total_pengeluaran += tx.amount

        rows.append({
            "Tanggal": dt_str,
            "Anggota": user_name,
            "Tipe": tx.type,
            "Nominal": tx.amount,
            "Keterangan": tx.description or "-"
        })

    sisa_saldo = total_pemasukan - total_pengeluaran

    # Buat DataFrame
    df = pd.DataFrame(rows)

    # Output stream
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Riwayat Tabungan", startrow=3)
        workbook = writer.book
        worksheet = writer.sheets["Riwayat Tabungan"]

        # Styling & Header Judul
        title_font = Font(name="Calibri", size=14, bold=True, color="1B4D3E")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="2D6A4F", end_color="2D6A4F", fill_type="solid")
        summary_title_fill = PatternFill(start_color="D8F3DC", end_color="D8F3DC", fill_type="solid")
        summary_font = Font(name="Calibri", size=11, bold=True)
        thin_border = Border(
            left=Side(style='thin', color='DDDDDD'),
            right=Side(style='thin', color='DDDDDD'),
            top=Side(style='thin', color='DDDDDD'),
            bottom=Side(style='thin', color='DDDDDD')
        )
        double_bottom_border = Border(
            top=Side(style='thin', color='000000'),
            bottom=Side(style='double', color='000000')
        )

        # Judul Laporan
        worksheet.merge_cells("A1:E1")
        title_cell = worksheet["A1"]
        title_cell.value = f"Laporan Tabungan Pasangan - Bismillah Nikah ({title_suffix})"
        title_cell.font = title_font
        title_cell.alignment = Alignment(horizontal="left", vertical="center")

        worksheet["A2"] = f"Digenerate pada: {datetime.now().strftime('%d %B %Y %H:%M:%S')}"
        worksheet["A2"].font = Font(name="Calibri", size=9, italic=True, color="666666")

        # Format Table Header (Row 4)
        for col_idx in range(1, 6):
            cell = worksheet.cell(row=4, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Format Data Rows
        start_data_row = 5
        total_rows = len(rows)
        end_data_row = start_data_row + total_rows - 1

        for r_idx in range(start_data_row, end_data_row + 1):
            # Tanggal
            c_date = worksheet.cell(row=r_idx, column=1)
            c_date.alignment = Alignment(horizontal="center")
            c_date.border = thin_border

            # Anggota
            c_user = worksheet.cell(row=r_idx, column=2)
            c_user.border = thin_border

            # Tipe
            c_type = worksheet.cell(row=r_idx, column=3)
            c_type.alignment = Alignment(horizontal="center")
            c_type.border = thin_border
            if c_type.value == "PEMASUKAN":
                c_type.font = Font(color="2D6A4F", bold=True)
            elif c_type.value == "PENGELUARAN":
                c_type.font = Font(color="C81D25", bold=True)

            # Nominal
            c_nominal = worksheet.cell(row=r_idx, column=4)
            c_nominal.number_format = '"Rp "#,##0'
            c_nominal.alignment = Alignment(horizontal="right")
            c_nominal.border = thin_border

            # Keterangan
            c_desc = worksheet.cell(row=r_idx, column=5)
            c_desc.border = thin_border

        # Baris Ringkasan Bawah
        summary_row_1 = end_data_row + 2
        worksheet.cell(row=summary_row_1, column=3, value="Total Pemasukan").font = summary_font
        worksheet.cell(row=summary_row_1, column=3).fill = summary_title_fill
        c_tot_in = worksheet.cell(row=summary_row_1, column=4, value=total_pemasukan)
        c_tot_in.font = Font(name="Calibri", size=11, bold=True, color="2D6A4F")
        c_tot_in.number_format = '"Rp "#,##0'
        c_tot_in.fill = summary_title_fill

        summary_row_2 = summary_row_1 + 1
        worksheet.cell(row=summary_row_2, column=3, value="Total Pengeluaran").font = summary_font
        worksheet.cell(row=summary_row_2, column=3).fill = summary_title_fill
        c_tot_out = worksheet.cell(row=summary_row_2, column=4, value=total_pengeluaran)
        c_tot_out.font = Font(name="Calibri", size=11, bold=True, color="C81D25")
        c_tot_out.number_format = '"Rp "#,##0'
        c_tot_out.fill = summary_title_fill

        summary_row_3 = summary_row_2 + 1
        worksheet.cell(row=summary_row_3, column=3, value="Sisa Saldo").font = summary_font
        worksheet.cell(row=summary_row_3, column=3).fill = summary_title_fill
        worksheet.cell(row=summary_row_3, column=3).border = double_bottom_border
        c_net = worksheet.cell(row=summary_row_3, column=4, value=sisa_saldo)
        c_net.font = Font(name="Calibri", size=12, bold=True, color="1B4D3E")
        c_net.number_format = '"Rp "#,##0'
        c_net.fill = summary_title_fill
        c_net.border = double_bottom_border

        # Auto-fit lebar kolom
        for col in worksheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if cell.row == 1:  # Abaikan judul yang dimerge
                    continue
                if len(val) > max_len:
                    max_len = len(val)
            worksheet.column_dimensions[col_letter].width = max(max_len + 4, 14)

    output.seek(0)
    return output
