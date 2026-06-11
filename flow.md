# Flow Project NLP2

Dokumen ini menjelaskan alur kerja sistem, struktur project, dan peran tiap file utama pada aplikasi scraper dan dashboard analisis ulasan Tokopedia.

## Ringkasan Sistem

Project ini berisi pipeline sederhana untuk mengambil ulasan produk dari Tokopedia, membersihkan teks, memberi label sentimen, menyimpan hasil ke CSV/JSON, lalu menampilkan hasilnya di dashboard desktop berbasis Tkinter.

Komponen utama:

- `main.py`: menu launcher untuk menjalankan scraper, dashboard, statistik, dependency check, dan cleanup.
- `scraper_ecomm_advanced.py`: scraper utama dengan Playwright, caching, retry, validasi review, sentiment analysis, dan export data.
- `dashboard.py`: dashboard desktop untuk membaca CSV dan menampilkan statistik/grafik.
- `scraper_ecomm.py`: scraper versi lama/sederhana, masih berguna sebagai referensi atau fallback.
- `dataset_ulasan_tokopedia.csv`: output CSV yang dibaca dashboard.
- `dataset_ulasan_tokopedia.json`: output JSON hasil scraping.
- `requirements_final.txt`: daftar dependency Python.

## Alur Sistem Utama

```text
User
  |
  v
main.py
  |
  +-- Option 1: Run scraper
  |     |
  |     v
  |   scraper_ecomm_advanced.py
  |     |
  |     +-- validasi URL dan konfigurasi scraping
  |     +-- buka Chromium lewat Playwright
  |     +-- aktifkan stealth mode
  |     +-- buka halaman produk Tokopedia
  |     +-- scroll dan buka section ulasan
  |     +-- ekstrak kandidat teks ulasan
  |     +-- filter noise/metadata halaman
  |     +-- ekstrak rating jika tersedia
  |     +-- analisis sentimen
  |     +-- deduplikasi review
  |     +-- simpan CSV dan JSON
  |
  +-- Option 2: Launch dashboard
  |     |
  |     v
  |   dashboard.py
  |     |
  |     +-- baca dataset_ulasan_tokopedia.csv
  |     +-- normalisasi kolom
  |     +-- hitung statistik
  |     +-- render grafik
  |     +-- tampilkan tabel data
  |
  +-- Option 3: View statistics
  |     |
  |     v
  |   baca CSV dan tampilkan ringkasan di terminal
```

## Flow Scraper

```text
Input URL produk
  |
  v
parse config
  |
  v
cek cache jika diaktifkan
  |
  +-- cache valid -> return data cache
  |
  v
launch browser
  |
  v
open product page
  |
  v
open/scroll review section
  |
  v
extract review candidates
  |
  +-- selector review spesifik Tokopedia
  +-- network JSON fallback
  +-- visible text fallback
  |
  v
sanitize text
  |
  v
validate review text
  |
  +-- buang metadata/noise seperti ringkasan rating, deskripsi produk, dan teks navigasi
  |
  v
extract rating
  |
  v
analyze sentiment
  |
  v
deduplicate by content hash
  |
  v
save CSV/JSON
```

## Flow Dashboard

```text
Start dashboard.py
  |
  v
load dataset_ulasan_tokopedia.csv
  |
  v
prepare_dataframe
  |
  +-- pastikan kolom review_text tersedia
  +-- rating dikonversi ke angka 0-5
  +-- sentiment dinormalisasi ke positive/negative/neutral
  +-- text_length dihitung jika tidak tersedia
  |
  v
update_dashboard
  |
  +-- update kartu statistik
  +-- render distribusi sentimen
  +-- render distribusi rating
  +-- render korelasi rating-sentimen
  +-- isi tabel review
```

## Struktur Project

```text
NLP2/
|-- main.py
|-- scraper_ecomm_advanced.py
|-- scraper_ecomm.py
|-- dashboard.py
|-- dataset_ulasan_tokopedia.csv
|-- dataset_ulasan_tokopedia.json
|-- requirements_final.txt
|-- README.md
|-- CHANGELOG.md
|-- SCRAPER_IMPROVEMENTS.md
|-- DASHBOARD_IMPROVEMENTS.md
|-- flow.md
|-- .gitignore
`-- nlp_env/
```

## Peran File

| File | Peran |
| --- | --- |
| `main.py` | Entry point berbasis menu untuk user non-teknis. |
| `scraper_ecomm_advanced.py` | Scraper utama dan pipeline ekstraksi data. |
| `scraper_ecomm.py` | Scraper versi awal, sebaiknya dianggap legacy/reference. |
| `dashboard.py` | GUI analitik untuk membaca dan memvisualisasikan CSV. |
| `dataset_ulasan_tokopedia.csv` | Dataset utama untuk dashboard. |
| `dataset_ulasan_tokopedia.json` | Export JSON untuk kebutuhan integrasi/manual check. |
| `requirements_final.txt` | Dependency Python yang perlu diinstall. |
| `.gitignore` | Daftar file/folder generated yang tidak perlu masuk Git. |

## Format Output Dataset

Kolom yang diharapkan:

| Kolom | Keterangan |
| --- | --- |
| `id` | Nomor urut data. |
| `review_text` | Teks ulasan yang sudah dibersihkan. |
| `rating` | Rating 0-5. Nilai 0 berarti rating tidak ditemukan. |
| `sentiment` | Label `positive`, `negative`, atau `neutral`. |
| `date_scraped` | Timestamp saat data diambil. |
| `text_length` | Panjang teks ulasan. |
| `source` | Sumber data, saat ini `tokopedia`. |
| `source_url` | URL asal review, ada pada mode multi-URL. |

## Cara Menjalankan

Gunakan Python dari virtual environment project:

```powershell
.\nlp_env\Scripts\python.exe main.py
```

Menjalankan scraper langsung:

```powershell
.\nlp_env\Scripts\python.exe scraper_ecomm_advanced.py --url "https://www.tokopedia.com/nama-toko/nama-produk" --max-reviews 100 --no-cache
```

Menjalankan dashboard:

```powershell
.\nlp_env\Scripts\python.exe dashboard.py
```

## Catatan Kualitas Data

Dashboard sangat bergantung pada kualitas `dataset_ulasan_tokopedia.csv`. Jika CSV berisi metadata halaman seperti `Detail Produk`, `Tentang Produk Ini`, atau semua rating bernilai `0`, berarti scraper belum mendapatkan section ulasan yang valid.

Saat kondisi itu terjadi:

- Jalankan ulang scraper tanpa cache.
- Pastikan URL produk memiliki ulasan.
- Jalankan mode non-headless agar halaman bisa dipantau.
- Cek debug snapshot jika scraper gagal menemukan ulasan.
- Perketat filter ekstraksi sebelum memakai dataset untuk analisis.

## File Generated Yang Tidak Perlu Disimpan

File/folder berikut bersifat generated dan bisa dibuat ulang:

- `__pycache__/`
- `scraper_cache/`
- `debug_*.png`
- `debug_*.html`
- `debug_*.txt`
- `*.pyc`

Virtual environment seperti `nlp_env/` juga tidak ideal masuk Git. Folder ini masih boleh ada secara lokal untuk menjalankan project, tetapi sebaiknya repository hanya menyimpan dependency list seperti `requirements_final.txt`.
