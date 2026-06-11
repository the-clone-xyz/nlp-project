# Panduan Teknis Pengembangan Sistem NLP2

Dokumen ini menjelaskan arsitektur, alur kerja, kontrak data, komponen kode, risiko teknis, dan rencana pengembangan lanjutan untuk project NLP2. Tujuannya adalah membantu developer berikutnya memahami sistem tanpa harus membaca seluruh kode dari awal.

## 1. Ringkasan Sistem

NLP2 adalah aplikasi desktop dan command-line untuk mengambil ulasan produk Tokopedia, membersihkan teks, memberi label sentimen, menyimpan hasil ke CSV/JSON, lalu menampilkan analisis dalam dashboard Tkinter.

Secara garis besar sistem terdiri dari:

| Komponen | File | Peran |
| --- | --- | --- |
| Launcher/menu | `main.py` | Entry point interaktif untuk user non-teknis. |
| Scraper utama | `scraper_ecomm_advanced.py` | Pipeline ekstraksi ulasan Tokopedia dengan Playwright. |
| Dashboard | `dashboard.py` | GUI analitik berbasis Tkinter dan Matplotlib. |
| Scraper lama | `scraper_ecomm.py` | Versi awal yang lebih sederhana, sebaiknya dianggap legacy/reference. |
| Dataset utama | `dataset_ulasan_tokopedia.csv` | Data utama yang dibaca dashboard. |
| Export JSON | `dataset_ulasan_tokopedia.json` | Data hasil scraping dalam format JSON. |
| Dependency | `requirements_final.txt` | Daftar package Python. |
| Dokumentasi alur | `flow.md` | Ringkasan alur project yang lebih singkat. |

Sistem ini belum memakai database dan belum memiliki backend API. Data disimpan langsung ke file lokal.

## 2. Cara Menjalankan Project

Gunakan Python dari virtual environment lokal:

```powershell
.\nlp_env\Scripts\python.exe main.py
```

Menjalankan dashboard langsung:

```powershell
.\nlp_env\Scripts\python.exe dashboard.py
```

Menjalankan scraper langsung untuk satu URL:

```powershell
.\nlp_env\Scripts\python.exe scraper_ecomm_advanced.py --url "https://www.tokopedia.com/nama-toko/nama-produk" --max-reviews 100 --no-cache
```

Menjalankan scraper dalam mode headless:

```powershell
.\nlp_env\Scripts\python.exe scraper_ecomm_advanced.py --url "https://www.tokopedia.com/nama-toko/nama-produk" --max-reviews 100 --headless
```

Menjalankan multi-URL:

```powershell
.\nlp_env\Scripts\python.exe scraper_ecomm_advanced.py --url "https://www.tokopedia.com/toko-a/produk-a" --url "https://www.tokopedia.com/toko-b/produk-b" --max-reviews 50
```

Jika dependency belum ada:

```powershell
.\nlp_env\Scripts\python.exe -m pip install -r requirements_final.txt
.\nlp_env\Scripts\python.exe -m playwright install chromium
```

## 3. Dependency Utama

Isi `requirements_final.txt`:

| Package | Fungsi |
| --- | --- |
| `pandas` | Membaca, membersihkan, menyimpan, dan menganalisis CSV. |
| `playwright` | Browser automation untuk membuka halaman Tokopedia. |
| `playwright_stealth` | Mengurangi indikasi browser otomatis. |
| `textblob` | Fallback analisis sentimen berbasis polaritas. |
| `matplotlib` | Grafik pada dashboard Tkinter. |
| `tkinter` | GUI desktop. Biasanya bawaan Python Windows, tidak ada di `requirements_final.txt`. |

## 4. Struktur Direktori

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
|-- DEVELOPMENT_GUIDE.md
|-- .gitignore
|-- scraper_cache/              # generated, diabaikan git
|-- __pycache__/                # generated, diabaikan git
`-- nlp_env/                    # virtual environment lokal, diabaikan git
```

## 5. Arsitektur Tingkat Tinggi

```text
User
  |
  v
main.py
  |
  +-- Option 1 -> scraper_ecomm_advanced.py
  |      |
  |      +-- validasi input URL
  |      +-- cek cache
  |      +-- buka browser Playwright
  |      +-- buka halaman produk
  |      +-- scroll dan buka section ulasan
  |      +-- ekstrak kandidat ulasan dari DOM
  |      +-- fallback dari response JSON/API
  |      +-- fallback dari teks terlihat
  |      +-- bersihkan teks
  |      +-- validasi review
  |      +-- ekstrak rating
  |      +-- analisis sentimen
  |      +-- deduplikasi
  |      +-- simpan CSV/JSON
  |
  +-- Option 2 -> dashboard.py
  |      |
  |      +-- baca CSV
  |      +-- normalisasi dataframe
  |      +-- hitung statistik
  |      +-- render chart
  |      +-- render tabel
  |
  +-- Option 3 -> statistik terminal dari CSV
```

## 6. Kontrak Data

Scraper menghasilkan list of dict, lalu disimpan sebagai CSV dan JSON. Dashboard membaca CSV sebagai sumber utama.

Kolom yang diharapkan:

| Kolom | Tipe | Wajib | Keterangan |
| --- | --- | --- | --- |
| `id` | integer | Ya | Nomor urut review. |
| `review_text` | string | Ya | Teks ulasan yang sudah dibersihkan. |
| `rating` | integer | Ya | Rating 1-5. Nilai `0` berarti rating tidak ditemukan. |
| `sentiment` | string | Ya | Salah satu dari `positive`, `negative`, `neutral`. |
| `date_scraped` | string | Ya | Timestamp saat scraping, format `YYYY-MM-DD HH:MM:SS`. |
| `text_length` | integer | Ya | Panjang karakter `review_text`. |
| `source` | string | Ya | Saat ini bernilai `tokopedia`. |
| `source_url` | string | Opsional | Ditambahkan pada mode multi-URL melalui `flatten_results`. |
| `nlp_tokens` | array/list | Ya | Hasil tahap tokenization dari `review_text`. |
| `nlp_no_stopwords` | array/list | Ya | Token setelah stopword removal. |
| `nlp_stems` | array/list | Ya | Token setelah stemming ringan Bahasa Indonesia. |
| `nlp_term_frequency` | object/dict | Ya | Frekuensi term per review setelah stemming. |
| `vector_terms` | array/list | Ya | Vocabulary corpus yang dipakai untuk vectorization. |
| `vector_values` | array/list | Ya | Nilai term-frequency review terhadap `vector_terms`. |
| `vec_*` | integer | Ya | Kolom numerik vectorization untuk fitur corpus teratas. |

Contoh data:

```json
{
  "id": 1,
  "review_text": "Produk bagus dan pengiriman cepat",
  "rating": 5,
  "sentiment": "positive",
  "date_scraped": "2026-05-22 11:37:34",
  "text_length": 33,
  "source": "tokopedia"
}
```

Dashboard cukup toleran terhadap CSV yang tidak lengkap:

- Jika `review_text` tidak ada, dashboard membuat kolom kosong.
- Jika `id` tidak ada, dashboard membuat nomor urut baru.
- Jika `rating` tidak valid, nilainya diubah menjadi `0`.
- Jika `sentiment` tidak valid, nilainya diubah menjadi `neutral`.
- Jika `text_length` tidak ada, nilainya dihitung dari panjang `review_text`.
- Jika kolom NLP belum ada, dashboard menghitung ulang Tokenization, Stopword Removal, Stemming, dan Vectorization dari `review_text`.

## 6.1 Tahapan NLP

Pipeline NLP yang ditambahkan:

| Tahap | Fungsi | Output |
| --- | --- | --- |
| Tokenization | `tokenize_text()` | `nlp_tokens` |
| Stopword Removal | `remove_stopwords()` | `nlp_no_stopwords` |
| Stemming | `stem_tokens()` dan `stem_indonesian_word()` | `nlp_stems` |
| Vectorization | `enrich_reviews_with_nlp()` | `nlp_term_frequency`, `vector_terms`, `vector_values`, dan `vec_*` |

Vectorization saat ini memakai term frequency sederhana tanpa dependency eksternal. Vocabulary corpus dibatasi oleh `NLP_VECTOR_MAX_FEATURES` di `scraper_ecomm_advanced.py`.

## 7. Detail `main.py`

`main.py` adalah launcher berbasis menu.

Fungsi utama:

| Fungsi | Peran |
| --- | --- |
| `print_banner()` | Menampilkan banner aplikasi. |
| `check_dependencies()` | Mengecek import package yang dibutuhkan. |
| `install_dependencies()` | Install package via pip dan install Chromium Playwright. |
| `prompt_scraper_options()` | Meminta URL, jumlah review, pilihan cache, dan headless mode. |
| `run_scraper()` | Memanggil `scrape_reviews_advanced`, lalu menyimpan CSV/JSON. |
| `run_dashboard()` | Memastikan dataset tersedia, lalu menjalankan dashboard. |
| `show_menu()` | Menampilkan menu utama. |
| `view_statistics()` | Membaca CSV dan menampilkan ringkasan statistik di terminal. |
| `cleanup_cache()` | Menghapus cache/debug file. |
| `show_help()` | Menampilkan bantuan penggunaan. |
| `main()` | Loop utama menu. |

Catatan pengembangan:

- `main.py` masih mencampur UI terminal, dependency installer, dan business flow.
- Untuk pengembangan besar, pisahkan logic CLI, service scraper, dan helper file ke module berbeda.
- `install_dependencies()` menggunakan daftar package hard-coded, belum membaca `requirements_final.txt`.
- Beberapa string banner/help pada file lama terlihat seperti mojibake di terminal tertentu. Untuk rilis, rapikan encoding file dan pastikan semua file disimpan sebagai UTF-8.

## 8. Detail `scraper_ecomm_advanced.py`

Ini adalah komponen terpenting dalam sistem.

### 8.1 Konfigurasi

Konstanta utama:

| Nama | Nilai Saat Ini | Fungsi |
| --- | --- | --- |
| `CACHE_DIR` | `scraper_cache` | Folder cache JSON per URL. |
| `CACHE_EXPIRY_HOURS` | `24` | Masa berlaku cache. |
| `DEFAULT_TARGET_URL` | URL produk contoh | URL default jika CLI tidak diberi URL. |
| `ScraperConfig.MAX_RETRIES` | `3` | Retry maksimal saat gagal. |
| `ScraperConfig.RETRY_DELAY_BASE` | `2` | Basis exponential backoff. |
| `ScraperConfig.SCROLL_ITERATIONS` | `15` | Maksimum scroll saat lazy-load terdeteksi. |
| `ScraperConfig.PAGE_LOAD_TIMEOUT` | `60000 ms` | Timeout load halaman. |
| `ScraperConfig.MAX_CONCURRENT_TASKS` | `2` | Batas scraping paralel. |
| `ScraperConfig.MIN_REVIEW_TEXT_LENGTH` | `5` | Panjang minimum kandidat review. |
| `ScraperConfig.REVIEW_LOAD_TIMEOUT` | `90 detik` | Waktu tunggu review section siap. |
| `ScraperConfig.HEADLESS` | `False` | Default browser terlihat. |

Saran pengembangan:

- Pindahkan konfigurasi ke file `.env`, `config.toml`, atau argumen CLI.
- Pisahkan konfigurasi runtime dan konfigurasi selector agar mudah diubah saat struktur Tokopedia berubah.

### 8.2 Preprocessing Teks

Fungsi penting:

| Fungsi | Peran |
| --- | --- |
| `sanitize_text(raw_text)` | Membersihkan HTML tag, karakter khusus, newline, dan spasi berlebih. |
| `tokenize_text(text)` | Tokenisasi ringan untuk Bahasa Indonesia. |
| `is_probably_review_text(text)` | Filter awal agar metadata halaman tidak masuk sebagai review. |
| `score_review_candidate(text)` | Memberi skor kandidat teks agar review murni diprioritaskan. |
| `is_strong_review_candidate(text)` | Filter lebih ketat untuk fallback teks halaman. |

Sistem memakai beberapa daftar kata:

- `POSITIVE_WORDS`
- `NEGATIVE_WORDS`
- `NEGATIONS`
- `INTENSIFIERS`
- `POSITIVE_PHRASES`
- `NEGATIVE_PHRASES`
- `NEUTRAL_PHRASES`
- `REVIEW_NOISE_PATTERNS`

Catatan kualitas:

- Pendekatan ini berbasis lexicon sederhana, cocok untuk baseline.
- Untuk dataset besar, pertimbangkan model Bahasa Indonesia seperti IndoBERT sentiment atau model klasifikasi yang dilatih khusus.
- `TextBlob` bukan alat utama yang ideal untuk Bahasa Indonesia, sehingga sebaiknya hanya dianggap fallback.

### 8.3 Ekstraksi Rating

Fungsi:

```text
extract_rating(rating_text) -> int
extract_rating_from_element(element) -> int
```

Rating dicari dari:

- `aria-label`
- `title`
- `alt`
- inner text elemen rating
- class/data-testid yang mengandung `rating`, `Rating`, `star`, atau `bintang`

Jika rating tidak ditemukan, nilai `0` digunakan. Ini penting karena `0` bukan rating asli, melainkan marker "tidak ditemukan".

### 8.4 Analisis Sentimen

Fungsi:

```text
analyze_sentiment(text) -> "positive" | "negative" | "neutral"
```

Urutan logika:

1. Teks dibersihkan dan ditokenisasi.
2. Phrase positif/negatif diberi bobot.
3. Kata positif/negatif diberi skor.
4. Negation seperti `tidak`, `gak`, `nggak` membalik skor kata setelahnya.
5. Intensifier seperti `sangat`, `banget`, `sekali` menaikkan bobot.
6. Jika skor >= 1, hasil `positive`.
7. Jika skor <= -1, hasil `negative`.
8. Jika tidak jelas, fallback ke `TextBlob`.
9. Jika tetap tidak jelas, hasil `neutral`.

Batasan:

- Belum ada confidence score.
- Belum ada evaluasi akurasi terhadap dataset berlabel manual.
- Belum membedakan sarkasme, slang baru, atau konteks produk.

### 8.5 Cache

Fungsi:

| Fungsi | Peran |
| --- | --- |
| `get_cache_file(url)` | Membuat nama file cache berdasarkan MD5 URL. |
| `is_cache_valid(cache_file)` | Mengecek umur cache. |
| `load_from_cache(url)` | Membaca cache dan memvalidasi isinya. |
| `save_to_cache(url, data)` | Menyimpan hasil scrape ke cache. |

Cache disimpan ke `scraper_cache/cache_<hash>.json` dan berlaku 24 jam.

Catatan:

- Cache hanya dipakai jika `use_cache=True`.
- Jika cache berisi data tidak valid, cache diabaikan.
- Folder cache sudah masuk `.gitignore`.

### 8.6 Alur Scraping Utama

Fungsi utama:

```text
scrape_reviews_advanced(url, max_reviews=100, use_cache=True, retry_count=0, headless=None)
```

Alur:

```text
Input URL
  |
  v
load cache jika aktif
  |
  +-- cache valid -> return data
  |
  v
launch Chromium
  |
  v
create context dengan viewport dan user-agent
  |
  v
pasang listener response network
  |
  v
aktifkan stealth
  |
  v
page.goto(url)
  |
  v
detect lazy loading
  |
  v
scroll halaman beberapa kali
  |
  v
open_review_section()
  |
  v
wait_for_review_content()
  |
  v
ekstraksi via selector DOM
  |
  +-- jika kosong -> fallback response JSON/API
  |
  +-- jika kosong -> fallback visible text
  |
  +-- jika tetap kosong -> simpan debug snapshot
  |
  v
validasi, sentiment, rating, dedupe
  |
  v
save cache jika aktif
  |
  v
return list review
```

### 8.7 Strategi Ekstraksi

Scraper memakai beberapa lapisan:

1. Selector spesifik Tokopedia:
   - `span[data-testid*="lblItemUlasan"]`
   - `[data-testid*="reviewContent"]`
   - `[data-testid*="ReviewCard"]`
   - `[data-testid*="ulasan"]`
   - dan variasi lain.

2. Selector generik:
   - elemen dengan class mengandung `review`
   - `article`
   - `div[role="article"]`
   - `.review-card`
   - `.feedback-item`

3. Network JSON fallback:
   - listener response menangkap URL yang mengandung `review`, `ulasan`, `graphql`, atau `pdp`
   - JSON di-walk secara rekursif untuk mencari field seperti `review`, `content`, `comment`, `message`, `text`, `ulasan`, `feedback`

4. Visible-text fallback:
   - mengambil teks dari elemen terlihat di halaman
   - filter ketat memakai `is_strong_review_candidate`

### 8.8 Deduplikasi

Fungsi:

```text
compute_content_hash(text)
```

Teks dinormalisasi lalu dibuat MD5. Hash ini dipakai untuk:

- menghapus duplikasi kandidat dalam satu elemen
- menghapus duplikasi antar selector
- menghapus duplikasi hasil final
- menghapus duplikasi cache/network fallback

### 8.9 Debug Snapshot

Saat tidak ada review valid, scraper memanggil:

```text
save_debug_snapshot(page, reason)
```

File debug yang mungkin dibuat:

- `debug_no_reviews_found.png`
- `debug_no_reviews_found.html`
- `debug_no_reviews_found.txt`
- variasi `debug_*.png/html/txt`

File ini sudah diabaikan oleh `.gitignore`.

### 8.10 Export

Fungsi:

| Fungsi | Output |
| --- | --- |
| `save_to_csv(data, filename)` | CSV UTF-8, sort berdasarkan `date_scraped` descending. |
| `save_to_json(data, filename)` | JSON UTF-8 dengan indentasi. |
| `print_statistics(data)` | Statistik scraping di terminal/log. |

### 8.11 CLI Scraper

Argumen:

| Argumen | Fungsi |
| --- | --- |
| `--url` | URL produk. Bisa diulang untuk multi-URL. |
| `--url-file` | File teks berisi satu URL per baris. |
| `--max-reviews` | Jumlah maksimum review per URL. Default `100`. |
| `--output-csv` | Path output CSV. Default `dataset_ulasan_tokopedia.csv`. |
| `--output-json` | Path output JSON. Default `dataset_ulasan_tokopedia.json`. |
| `--no-cache` | Paksa scrape baru. |
| `--headless` | Jalankan Chromium tanpa UI. |

Untuk multi-URL, `scrape_multiple_urls()` memakai `asyncio.Semaphore` dengan batas `MAX_CONCURRENT_TASKS = 2`.

## 9. Detail `dashboard.py`

Dashboard adalah aplikasi desktop berbasis Tkinter.

### 9.1 Struktur UI

Class utama:

```text
DashboardApp
```

Method penting:

| Method | Peran |
| --- | --- |
| `__init__()` | Setup window, style, state, dan load data. |
| `setup_styles()` | Konfigurasi tema ttk dan warna. |
| `create_card()` | Helper card dengan border. |
| `clear_frame()` | Membersihkan frame dan menutup figure Matplotlib. |
| `create_widgets()` | Membuat header, toolbar, dan tab utama. |
| `create_overview_tab()` | Tab ringkasan statistik dan chart. |
| `create_sentiment_tab()` | Tab grafik sentimen. |
| `create_rating_tab()` | Tab grafik rating. |
| `create_analytics_tab()` | Tab korelasi rating-sentimen. |
| `create_text_tab()` | Tab analisis teks. Saat ini berupa placeholder. |
| `create_data_tab()` | Tabel review. |
| `load_data()` | Membaca `dataset_ulasan_tokopedia.csv`. |
| `load_csv_file()` | Memuat CSV manual dari file picker. |
| `prepare_dataframe()` | Normalisasi kolom dan tipe data. |
| `valid_rating_series()` | Mengambil rating valid 1-5. |
| `count_suspicious_rows()` | Menghitung indikasi metadata/noise dalam review. |
| `update_quality_message()` | Menampilkan status kualitas data. |
| `update_dashboard()` | Memanggil semua fungsi render. |
| `update_stats()` | Menghitung nilai kartu statistik. |
| `draw_overview_charts()` | Pie/bar/histogram ringkasan. |
| `draw_sentiment_chart()` | Bar chart sentimen. |
| `draw_rating_chart()` | Bar chart rating. |
| `draw_analytics_chart()` | Crosstab rating vs sentimen. |
| `draw_text_chart()` | Placeholder analisis teks. |
| `update_data_table()` | Mengisi treeview tabel data. |
| `refresh_dashboard()` | Reload CSV lokal. |
| `export_report()` | Saat ini masih placeholder/info dialog. |

### 9.2 Tab Dashboard

| Tab | Isi |
| --- | --- |
| `Ringkasan` | Kualitas data, total review, rata-rata rating, jumlah sentimen, chart ringkasan. |
| `Sentimen` | Kartu jumlah sentimen dan chart sentimen. |
| `Rating` | Distribusi rating 1-5. |
| `Korelasi Data` | Hubungan rating dengan sentimen. |
| `Analisis Teks` | Saat ini placeholder; distribusi teks ada di ringkasan. |
| `Tabel Data` | Treeview berisi ID, review, rating, sentiment, length, status. |

### 9.3 Validasi Data di Dashboard

Dashboard menilai kualitas data dengan:

- jumlah total baris
- jumlah rating valid 1-5
- indikasi metadata/noise di `review_text`

Pattern noise dashboard:

```text
diambil dari tokopedia
tiktok shop
pembeli merasa puas
rating
ulasan
```

Jika total baris kurang dari 5 atau ada metadata mencurigakan, dashboard menampilkan status kualitas rendah.

Catatan:

- Saat ini dashboard dapat menampilkan data dengan rating `0`, tetapi rating `0` tidak dihitung sebagai rating valid.
- `source_url` belum ditampilkan di tabel, walaupun tersedia pada mode multi-URL.
- `export_report()` belum benar-benar membuat file HTML; masih berupa placeholder.

## 10. Detail `scraper_ecomm.py`

`scraper_ecomm.py` adalah scraper lama dengan fungsi:

| Fungsi | Peran |
| --- | --- |
| `sanitize_text()` | Membersihkan teks dasar. |
| `scrape_reviews()` | Scrape sederhana dengan Playwright. |
| `save_to_csv()` | Simpan CSV. |
| `main()` | Entry point lama. |

Status rekomendasi:

- Jangan jadikan file ini sebagai jalur utama pengembangan.
- Simpan sebagai referensi untuk memahami versi awal.
- Jika tidak lagi dipakai, pindahkan ke folder `legacy/` atau hapus setelah ada backup/history Git yang jelas.

## 11. File Generated dan Git

`.gitignore` saat ini mengabaikan:

```text
__pycache__/
*.py[cod]
scraper_cache/
debug_*.png
debug_*.html
debug_*.txt
debug_page.html
nlp_env/
.venv/
venv/
env/
*.log
*.tmp
```

Rekomendasi:

- Jangan commit `nlp_env/`.
- Jangan commit cache/debug kecuali sedang melampirkan contoh bug.
- Dataset bisa dicommit jika memang dianggap sample data kecil. Untuk data besar, simpan di storage terpisah atau folder ignored.

## 12. Kondisi Data Saat Ini

Pada pengecekan terakhir, `dataset_ulasan_tokopedia.csv` berisi 5 baris dengan semua sentimen `neutral` dan semua rating `0`.

Beberapa contoh teks saat ini adalah:

- `Ada masalah dengan produk ini?`
- `Tentang Produk Ini`
- `Detail Produk`

Ini mengindikasikan dataset saat ini lebih mirip metadata/teks halaman daripada review pembeli yang valid. Untuk analisis yang serius, jalankan ulang scraper pada URL produk yang memiliki ulasan dan gunakan `--no-cache`.

## 13. Risiko Teknis

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| Struktur DOM Tokopedia berubah | Selector gagal menemukan review. | Pisahkan selector ke konfigurasi dan tambah test dengan snapshot HTML. |
| Bot detection | Page tidak memuat review atau kena blokir. | Rate limiting, headless/non-headless testing, user-agent rotation, dan fallback network. |
| Lazy loading/skeleton | Scraper mengambil metadata sebelum review muncul. | Perkuat `wait_for_review_content()` dan validasi elemen review. |
| Sentimen kurang akurat | Dashboard memberi insight yang salah. | Buat dataset berlabel manual dan evaluasi model. |
| Rating sering `0` | Analisis rating tidak berguna. | Perbaiki selector rating dan ekstraksi structured data. |
| CSV rusak/kolom hilang | Dashboard error atau hasil bias. | Tambah schema validation eksplisit sebelum render. |
| GUI monolitik | Sulit ditest dan dikembangkan. | Pisahkan data service, chart renderer, dan widget. |
| Export report placeholder | User mengira report sudah tersedia. | Implementasikan export HTML atau sembunyikan tombol sampai siap. |

## 14. Rekomendasi Refactor

Struktur yang lebih mudah dikembangkan:

```text
NLP2/
|-- app/
|   |-- __init__.py
|   |-- cli.py
|   |-- config.py
|   |-- models.py
|   |-- storage.py
|   |-- sentiment.py
|   |-- scraper/
|   |   |-- __init__.py
|   |   |-- tokopedia.py
|   |   |-- selectors.py
|   |   `-- cache.py
|   `-- dashboard/
|       |-- __init__.py
|       |-- app.py
|       |-- charts.py
|       `-- dataframe.py
|-- tests/
|   |-- test_sentiment.py
|   |-- test_sanitize.py
|   |-- test_validate_review.py
|   |-- test_dashboard_dataframe.py
|   `-- fixtures/
|-- main.py
|-- requirements.txt
`-- README.md
```

Prioritas refactor:

1. Pindahkan logika sentimen ke `sentiment.py`.
2. Pindahkan schema data dan validasi review ke `models.py`.
3. Pindahkan cache dan export ke `storage.py`.
4. Pindahkan selector Tokopedia ke `scraper/selectors.py`.
5. Pecah dashboard menjadi data preparation dan rendering.

## 15. Rekomendasi Testing

Belum terlihat test otomatis di repository. Minimal test yang disarankan:

### 15.1 Unit Test Preprocessing

Target:

- `sanitize_text()`
- `tokenize_text()`
- `is_probably_review_text()`
- `is_strong_review_candidate()`
- `compute_content_hash()`

Contoh kasus:

- HTML tag terhapus.
- Spasi berlebih menjadi satu spasi.
- Teks metadata seperti `Detail Produk` ditolak.
- Review valid seperti `Barang bagus, pengiriman cepat` diterima.
- Hash sama untuk teks yang berbeda hanya pada spasi/case.

### 15.2 Unit Test Sentiment

Target:

- `analyze_sentiment()`

Contoh:

| Input | Expected |
| --- | --- |
| `barang bagus dan pengiriman cepat` | `positive` |
| `barang rusak dan saya kecewa` | `negative` |
| `produk biasa saja` | `neutral` |
| `tidak bagus` | `negative` |
| `tidak mengecewakan` | `positive` atau minimal tidak `negative`, tergantung aturan yang dipilih |

### 15.3 Unit Test Dataframe Dashboard

Target:

- `prepare_dataframe()`
- `valid_rating_series()`
- `count_suspicious_rows()`

Contoh:

- CSV tanpa `id` tetap dibuatkan ID.
- Rating string dikonversi ke int.
- Rating di luar 0-5 menjadi 0.
- Sentiment aneh menjadi `neutral`.

### 15.4 Integration Test Scraper

Karena Tokopedia dinamis, test sebaiknya tidak bergantung langsung pada internet untuk CI. Gunakan:

- fixture HTML tersimpan
- fixture JSON response API
- mock Playwright page untuk unit kecil
- test manual terjadwal untuk URL nyata

## 16. Roadmap Pengembangan

### Tahap 1: Stabilitas Data

- Perbaiki filter agar metadata seperti `Detail Produk` tidak masuk dataset.
- Tambahkan validasi minimum review sebelum file lama ditimpa.
- Tambahkan summary kualitas data setelah scraping.
- Tambahkan test untuk preprocessing dan validasi review.

### Tahap 2: Kualitas Sentimen

- Buat sample dataset berlabel manual.
- Ukur akurasi lexicon saat ini.
- Tambahkan confidence score.
- Pertimbangkan model Bahasa Indonesia jika akurasi lexicon rendah.

### Tahap 3: Dashboard

- Implementasikan `export_report()` menjadi HTML nyata.
- Tampilkan `source_url` pada mode multi-URL.
- Tambahkan filter/search di tabel data.
- Tambahkan tab analisis teks yang benar-benar berisi word frequency, top terms, dan panjang review.

### Tahap 4: Packaging

- Rapikan struktur module.
- Ganti `requirements_final.txt` menjadi `requirements.txt` atau `pyproject.toml`.
- Tambahkan instruksi setup dari nol.
- Tambahkan test otomatis.

### Tahap 5: Storage dan Integrasi

- Pertimbangkan SQLite untuk menyimpan histori scraping.
- Tambahkan unique key berbasis `source_url + content_hash`.
- Tambahkan export Excel.
- Tambahkan API lokal jika nanti dashboard ingin dibuat web.

## 17. Checklist Developer Baru

Saat mulai mengembangkan project ini:

1. Jalankan `git status --short` dan pastikan memahami perubahan lokal.
2. Jalankan dependency check:

   ```powershell
   .\nlp_env\Scripts\python.exe -c "import pandas, playwright, playwright_stealth, textblob, matplotlib, tkinter; print('OK')"
   ```

3. Jalankan menu:

   ```powershell
   .\nlp_env\Scripts\python.exe main.py
   ```

4. Cek statistik dataset lewat menu option 3.
5. Jalankan dashboard:

   ```powershell
   .\nlp_env\Scripts\python.exe dashboard.py
   ```

6. Jika perlu scrape ulang, gunakan:

   ```powershell
   .\nlp_env\Scripts\python.exe scraper_ecomm_advanced.py --url "URL_PRODUK" --max-reviews 100 --no-cache
   ```

7. Setelah scraping, cek apakah review benar-benar review pembeli, bukan metadata halaman.
8. Jangan commit `nlp_env/`, `__pycache__/`, `scraper_cache/`, atau `debug_*`.

## 18. Definisi "Data Layak Analisis"

Sebelum dataset dipakai untuk mengambil kesimpulan, pastikan:

- Minimal ada jumlah review yang cukup untuk produk yang dianalisis.
- Mayoritas `review_text` adalah pengalaman pembeli, bukan teks halaman.
- Rating valid 1-5 tersedia untuk sebagian besar review jika analisis rating dibutuhkan.
- Sentiment tidak 100% `neutral` kecuali memang review sangat netral.
- Tidak ada duplikasi review dominan.
- Tanggal scraping jelas.
- Jika multi-URL, `source_url` tersedia agar data dapat ditelusuri.

## 19. Prioritas Perbaikan Terdekat

Prioritas paling pragmatis untuk pengembangan berikutnya:

1. Perkuat `is_probably_review_text()` agar teks seperti `Detail Produk`, `Tentang Produk Ini`, dan pertanyaan UI tidak lolos.
2. Tambah test unit untuk validasi review dan sentimen.
3. Implementasikan export HTML pada dashboard atau nonaktifkan tombol sampai fiturnya selesai.
4. Pisahkan daftar selector ke konfigurasi agar maintenance scraper lebih mudah.
5. Tambahkan kolom `content_hash` dan `source_url` ke output utama untuk tracking dan deduplikasi lintas run.

## 20. Kesimpulan Arsitektur

Project ini sudah memiliki pipeline end-to-end:

```text
Tokopedia -> Playwright scraper -> cleaning/sentiment -> CSV/JSON -> Tkinter dashboard
```

Bagian yang paling bernilai untuk dikembangkan adalah kualitas ekstraksi dan validasi data. Dashboard sudah cukup untuk eksplorasi awal, tetapi insight yang dihasilkan sangat bergantung pada apakah scraper benar-benar mengambil review pembeli. Karena itu, pengembangan berikutnya sebaiknya dimulai dari stabilisasi scraper, test validasi data, lalu peningkatan dashboard.
