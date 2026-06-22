# Flow Project NLP2

Dokumen ini menjelaskan alur sistem terbaru untuk scraper ulasan Tokopedia, pipeline NLP, penyimpanan dataset, dan dashboard browser yang dipakai untuk presentasi project.

## Ringkasan Sistem

NLP2 mengambil ulasan produk Tokopedia, membersihkan teks, menjalankan tahapan NLP, menyimpan hasil ke CSV/JSON, lalu menampilkan proses dan hasil analisis di dashboard web.

Fokus sistem saat ini:

- Mengambil data real dari halaman produk/review Tokopedia.
- Menghindari data dummy atau metadata halaman seperti `Detail Produk`.
- Menjalankan pipeline NLP: Tokenization, Stopword Removal, Stemming, dan Vectorization.
- Menampilkan alur bertahap di GUI agar mudah dijelaskan saat presentasi.

## Komponen Utama

| File | Peran |
| --- | --- |
| `web_dashboard.py` | Dashboard browser utama, endpoint API data, endpoint scraper, log scraping, dan tampilan alur presentasi. |
| `scraper_ecomm_advanced.py` | Scraper utama, fallback HTTP Tokopedia, validasi review, sentiment analysis, NLP enrichment, export CSV/JSON. |
| `main.py` | Launcher CLI/menu untuk menjalankan scraper, dashboard desktop, statistik, dependency check, dan cleanup. |
| `dashboard.py` | Dashboard desktop Tkinter legacy. Masih bisa dipakai, tetapi dashboard utama sekarang `web_dashboard.py`. |
| `scraper_ecomm.py` | Scraper versi awal/legacy. |
| `dataset_ulasan_tokopedia.csv` | Dataset utama yang dibaca dashboard browser. |
| `dataset_ulasan_tokopedia.json` | Export JSON hasil scraping. |
| `requirements_final.txt` | Dependency Python, termasuk `curl_cffi` untuk fallback HTTP. |

## Alur Besar Sistem

```text
User
  |
  v
web_dashboard.py
  |
  +-- Tab 1 Ringkasan
  |     +-- status dataset
  |     +-- ringkasan jumlah review, rating, sentimen, vocabulary
  |     +-- panel Alur Project untuk presentasi
  |
  +-- Tab 2 Scraping
  |     +-- input URL produk Tokopedia
  |     +-- pilih max_reviews, cache, dan mode browser
  |     +-- jalankan worker scraper
  |     +-- tampilkan log tahapan scraping
  |
  +-- Tab 3 Data Mentah
  |     +-- tampilkan review_text, rating, sentimen, sumber, tanggal
  |     +-- pencarian review/token/sentimen
  |
  +-- Tab 4 NLP
  |     +-- tampilkan contoh alur dari satu ulasan
  |     +-- tampilkan Tokenization
  |     +-- tampilkan Stopword Removal
  |     +-- tampilkan Stemming
  |     +-- tampilkan Vectorization
  |
  +-- Tab 5 Rating
  |     +-- distribusi rating
  |
  +-- Tab 6 Sentimen
        +-- distribusi positive/neutral/negative
```

## Alur Scraping Terbaru

Scraper sekarang punya dua jalur. Jalur pertama lebih cepat dan lebih stabil untuk Tokopedia karena tidak bergantung pada `page.goto()` Playwright.

```text
Input URL produk / short-link
  |
  v
normalize URL
  |
  v
resolve short-link tk.tokopedia.com
  |
  v
cek cache jika diaktifkan
  |
  +-- cache valid -> return data cache
  |
  v
HTTP fallback via curl_cffi
  |
  +-- impersonate Chrome
  +-- buka halaman /review
  +-- parse SSR cache window.__cache
  +-- ambil reviewListPDPType
  |
  +-- berhasil -> enrich NLP -> save CSV/JSON
  |
  v
Fallback Playwright
  |
  +-- launch Chromium headless jika tidak ada DISPLAY/XServer
  +-- context locale id-ID dan timezone Asia/Jakarta
  +-- service worker diblok agar response network bisa ditangkap
  +-- capture response review/graphql/pdp/rating
  +-- buka halaman dengan strategi commit/domcontentloaded
  +-- scroll dan buka section ulasan
  +-- selector extraction
  +-- network JSON fallback
  +-- visible text fallback
  |
  v
sanitize -> validate -> sentiment -> deduplicate -> enrich NLP -> save
```

### Kenapa Ada HTTP Fallback

Pada beberapa environment, Playwright dapat gagal dengan:

```text
Page.goto: Timeout ... waiting until "commit"
```

atau sebelumnya:

```text
net::ERR_HTTP2_PROTOCOL_ERROR
```

Karena itu scraper menggunakan `curl_cffi` untuk mengambil halaman `/review` dengan Chrome impersonation. Untuk halaman review Tokopedia, data komentar sering sudah tersedia di SSR cache dalam bentuk `reviewListPDPType`, sehingga review bisa diambil tanpa menunggu browser render penuh.

## Alur NLP

Setiap review yang valid diproses menjadi fitur NLP.

```text
review_text
  |
  v
Tokenization
  |
  +-- teks dipecah menjadi token/kata
  |
  v
Stopword Removal
  |
  +-- kata umum seperti "yang", "dan", "di", "ke" dihapus
  |
  v
Stemming
  |
  +-- token diubah ke bentuk dasar sederhana
  |
  v
Term Frequency
  |
  +-- hitung frekuensi setiap stem dalam review
  |
  v
Vectorization
  |
  +-- vocabulary corpus dibuat dari term paling sering
  +-- setiap review diubah menjadi vector numerik
  +-- nilai vector menunjukkan frekuensi term pada review tersebut
```

Contoh tampilan Vectorization di GUI:

```text
term      baik  packing  tv  barang  aman
value       1        0   0       1     1
```

Di GUI, vector tidak lagi ditampilkan sebagai tabel horizontal panjang. Vector ditampilkan sebagai grid compact `term -> nilai`, dengan nilai `0` dibuat redup agar tidak bergempetan dan lebih mudah dibaca.

## Alur GUI Untuk Presentasi

Dashboard browser dirancang agar bisa dipakai untuk menjelaskan project secara berurutan.

```text
1 Ringkasan
  |
  +-- Apa status dataset?
  +-- Berapa review berhasil diambil?
  +-- Berapa vocabulary NLP?

2 Scraping
  |
  +-- Masukkan URL produk
  +-- Jalankan scraping
  +-- Tunjukkan log proses

3 Data Mentah
  |
  +-- Tunjukkan teks review asli
  +-- Tunjukkan rating, sentimen, sumber, tanggal

4 NLP
  |
  +-- Tunjukkan contoh satu ulasan
  +-- Jelaskan Tokenization
  +-- Jelaskan Stopword Removal
  +-- Jelaskan Stemming
  +-- Jelaskan Vectorization

5 Rating
  |
  +-- Jelaskan distribusi bintang

6 Sentimen
  |
  +-- Jelaskan hasil klasifikasi sentimen
```

Setiap judul tahap NLP di GUI memiliki tooltip `?`:

- `Tokenization ?`
- `Stopword Removal ?`
- `Stemming ?`
- `Vectorization ?`

Saat `?` disorot, dashboard menampilkan pengertian singkat tahap tersebut.

## Format Output Dataset

Kolom utama:

| Kolom | Keterangan |
| --- | --- |
| `id` | Nomor urut review. |
| `review_text` | Teks ulasan yang sudah dibersihkan. |
| `rating` | Rating 0-5. |
| `sentiment` | Label `positive`, `negative`, atau `neutral`. |
| `date_scraped` | Timestamp review atau waktu scraping. |
| `text_length` | Panjang karakter review. |
| `source` | Sumber data, misalnya `tokopedia_review_page`. |
| `feedback_id` | ID feedback dari halaman review Tokopedia jika tersedia. |
| `review_timestamp_label` | Label waktu dari Tokopedia, misalnya `Lebih dari 1 tahun lalu`. |

Kolom NLP:

| Kolom | Keterangan |
| --- | --- |
| `nlp_tokens` | Hasil tokenization. |
| `nlp_no_stopwords` | Token setelah stopword removal. |
| `nlp_stems` | Token setelah stemming. |
| `nlp_term_frequency` | Frekuensi term per review. |
| `vector_terms` | Vocabulary corpus yang dipakai untuk vectorization. |
| `vector_values` | Nilai term-frequency review terhadap `vector_terms`. |
| `vec_*` | Kolom numerik per term untuk analisis lanjutan. |

## Cara Menjalankan

Install dependency:

```bash
python -m pip install -r requirements_final.txt
python -m playwright install chromium
```

Menjalankan dashboard browser utama:

```bash
python web_dashboard.py
```

Buka:

```text
http://127.0.0.1:8000
```

Menjalankan scraper langsung:

```bash
python scraper_ecomm_advanced.py --url "https://www.tokopedia.com/nama-toko/nama-produk" --max-reviews 100 --no-cache --headless
```

Menjalankan launcher CLI:

```bash
python main.py
```

## Catatan Kualitas Data

Dataset valid harus berisi review asli dari pengguna. Contoh data yang tidak valid:

- `Detail Produk`
- `Tentang Produk Ini`
- `Ada masalah dengan produk ini?`
- ringkasan rating tanpa teks komentar

Jika data seperti itu muncul:

- Jalankan ulang scraper tanpa cache.
- Gunakan URL produk langsung atau short-link Tokopedia yang valid.
- Pastikan produk memang memiliki ulasan teks.
- Cek log pada tab `2 Scraping`.
- Pastikan dependency `curl_cffi` sudah terpasang.

## File Generated Yang Tidak Perlu Disimpan

File/folder berikut bersifat generated dan bisa dibuat ulang:

- `__pycache__/`
- `scraper_cache/`
- `debug_*.png`
- `debug_*.html`
- `debug_*.txt`
- `*.pyc`

Virtual environment seperti `nlp_env/` juga tidak ideal masuk Git. Repository cukup menyimpan daftar dependency di `requirements_final.txt`.
