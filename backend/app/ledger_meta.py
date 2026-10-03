"""
Pondasi pembukuan ReNee Ponsel (hasil obrolan mentor).
SATU buku besar pusat, aliran uang dibedakan per fungsi (A-G).

A. PENDAPATAN (omzet): A1 Jasa Service, A2 Accessories, A3 Penjualan Unit, A4 Pendapatan Lain
B. HPP / MODAL BARANG: B1 Sparepart, B2 Accessories, B3 Unit
C. OPERASIONAL: C1 Gaji & Upah, C2 Tempat, C3 Internet & Sistem, C4 Operasional Harian, C5 Marketing, C6 Maintenance
D. ASET / INVESTASI
E. OWNER: E1 Modal Owner (masuk), E2 Prive (keluar)
F. NON-PENDAPATAN/NON-BIAYA: F1 Transfer Antar Kas, F2 Hutang/Pinjaman, F3 DP/Titipan
G. MEDIA UANG: kas_utama, kas_kecil, bank, qris

Rumus: Omzet(A) - HPP(B) = Laba Kotor; Laba Kotor - Operasional(C) = Laba Bersih.
Komisi teknisi = HPP jasa (biaya langsung service), bukan operasional.
"""
from typing import Dict, Optional

KELOMPOK = {
    "omzet": "Pendapatan (Omzet)",
    "hpp": "HPP / Modal Barang",
    "operasional": "Operasional Toko",
    "aset": "Aset / Investasi",
    "owner": "Transaksi Owner",
    "non": "Non-Pendapatan / Non-Biaya",
}

KATEGORI: Dict[str, Dict[str, str]] = {
    "A1": {"nama": "Jasa Service", "kelompok": "omzet"},
    "A2": {"nama": "Accessories", "kelompok": "omzet"},
    "A3": {"nama": "Penjualan Unit", "kelompok": "omzet"},
    "A4": {"nama": "Pendapatan Lain", "kelompok": "omzet"},
    "B1": {"nama": "Sparepart", "kelompok": "hpp"},
    "B2": {"nama": "Accessories", "kelompok": "hpp"},
    "B3": {"nama": "Unit", "kelompok": "hpp"},
    "C1": {"nama": "Gaji & Upah", "kelompok": "operasional"},
    "C2": {"nama": "Tempat (sewa/listrik/air)", "kelompok": "operasional"},
    "C3": {"nama": "Internet & Sistem", "kelompok": "operasional"},
    "C4": {"nama": "Operasional Harian", "kelompok": "operasional"},
    "C5": {"nama": "Marketing", "kelompok": "operasional"},
    "C6": {"nama": "Maintenance", "kelompok": "operasional"},
    "D": {"nama": "Aset / Investasi", "kelompok": "aset"},
    "E1": {"nama": "Modal Owner", "kelompok": "owner"},
    "E2": {"nama": "Prive / Pengambilan Owner", "kelompok": "owner"},
    "F1": {"nama": "Transfer Antar Kas", "kelompok": "non"},
    "F2": {"nama": "Hutang / Pinjaman", "kelompok": "non"},
    "F3": {"nama": "DP / Titipan", "kelompok": "non"},
}

MEDIA: Dict[str, str] = {
    "kas_utama": "Kas Utama (laci kasir)",
    "kas_kecil": "Kas Kecil (operasional harian)",
    "bank": "Rekening Bank",
    "qris": "QRIS / E-Wallet",
    # Bukan tempat uang: dipakai HPP yang terbentuk tanpa gerak kas
    # (kas sudah keluar saat beli). Otomatis dikecualikan dari saldo kas.
    "stok": "Persediaan/Stok (tanpa gerak kas)",
}

JENIS = ["masuk", "keluar", "transfer"]

# Sub-pemisah untuk D (tab Aset vs Investasi)
SUB_D = ["Aset", "Investasi"]

# Kode mentor yang boleh dipakai form Pengeluaran (belanja = HPP/aset, sisanya operasional)
KAT_EXPENSE_NEW = {
    "B1": "Belanja Sparepart (HPP)",
    "B2": "Belanja Accessories (HPP)",
    "C1": "Gaji & Upah",
    "C2": "Tempat (sewa/listrik/air)",
    "C3": "Internet & Sistem",
    "C4": "Operasional Harian",
    "C5": "Marketing",
    "C6": "Maintenance",
    "D": "Aset / Investasi",
}

# Metode bayar lama -> media G (agar dual-write expense/income otomatis punya media)
METODE_KE_MEDIA = {"Tunai": "kas_utama", "Transfer": "bank", "QRIS": "qris"}

# Kategori pengeluaran lama (7 macam) -> kode mentor
EXPENSE_CAT_MAP = {
    "Sewa": "C2",
    "Listrik": "C2",
    "Internet": "C3",
    "Gaji": "C1",
    "Belanja Part": "B1",
    "Operasional": "C4",
    "Lainnya": "C4",
}

# Kategori pemasukan manual lama (3 macam) -> kode mentor
INCOME_CAT_MAP = {
    "Modal Awal": "E1",
    "Tambahan Modal": "E1",
    "Pemasukan Lain": "A4",
}

KAS_KECIL_DEFAULT = 500000


def kelompok_of(kode: str) -> Optional[str]:
    m = KATEGORI.get(kode)
    return m["kelompok"] if m else None


def validate_entry(kategori: str, jenis: str, nominal: int, media: str,
                   media_tujuan: Optional[str] = None) -> Optional[str]:
    """Kembalikan pesan error jika tidak valid, None jika OK."""
    if kategori not in KATEGORI:
        return "kategori harus kode mentor: " + "/".join(sorted(KATEGORI.keys()))
    if jenis not in JENIS:
        return "jenis harus masuk/keluar/transfer"
    if not isinstance(nominal, int) or nominal <= 0:
        return "nominal harus > 0"
    if media not in MEDIA:
        return "media harus: " + "/".join(sorted(MEDIA.keys()))
    if kategori == "F1":
        if jenis != "transfer":
            return "F1 Transfer Antar Kas wajib jenis=transfer (bukan omzet, hanya pindah media)"
        if not media_tujuan or media_tujuan not in MEDIA:
            return "F1 wajib media_tujuan yang valid"
        if media_tujuan == media:
            return "F1 media_tujuan harus beda dari media asal"
    elif jenis == "transfer":
        return "jenis=transfer hanya untuk F1 Transfer Antar Kas"
    if kategori == "E1" and jenis != "masuk":
        return "E1 Modal Owner wajib jenis=masuk (bukan omzet)"
    if kategori == "E2" and jenis != "keluar":
        return "E2 Prive wajib jenis=keluar (bukan biaya operasional)"
    return None
