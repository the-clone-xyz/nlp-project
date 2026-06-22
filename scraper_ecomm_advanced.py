import asyncio
import argparse
import csv
try:
    import pandas as pd
except ImportError:
    pd = None
try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None
import re
import random
import json
import hashlib
import logging
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from datetime import datetime, timedelta
from textblob import TextBlob
from typing import List, Dict, Optional, Tuple
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ==========================================
# 0. LOGGING & CONFIG SETUP
# ==========================================
# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

DEFAULT_HTTP_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}


def can_launch_headed_browser() -> bool:
    """Return False in Linux server environments that do not expose a display."""
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def normalize_url(url: str) -> str:
    """Drop fragments and normalize whitespace so the same product URL caches consistently."""
    cleaned = str(url or "").strip()
    if not cleaned:
        return cleaned

    parts = urlsplit(cleaned)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def build_review_page_url(url: str) -> str:
    """Build Tokopedia product review page URL from a product URL."""
    parts = urlsplit(normalize_url(url))
    path = parts.path.rstrip("/")
    if not path.endswith("/review"):
        path = f"{path}/review"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def resolve_short_url(url: str) -> str:
    """Resolve Tokopedia short links before handing the URL to Chromium."""
    url = normalize_url(url)
    if "tk.tokopedia.com" not in url.lower():
        return url

    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": DESKTOP_USER_AGENT, **DEFAULT_HTTP_HEADERS},
    )
    opener = urllib.request.build_opener(NoRedirectHandler)
    try:
        opener.open(request, timeout=15)
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location")
        if location:
            logger.info("Resolved Tokopedia short link to product URL.")
            return normalize_url(urllib.request.urljoin(url, location))
    except Exception as exc:
        logger.warning(f"Short-link resolve failed, using original URL: {exc}")

    return url


def extract_reviews_from_review_page_html(html_text: str, max_reviews: int) -> List[Dict]:
    """Extract SSR review records from Tokopedia /review page cache."""
    reviews = []
    seen = set()
    pattern = re.compile(
        r'"reviewListPDPType\d+":(\{.*?"__typename":"reviewListPDPType"\})',
        re.DOTALL,
    )

    for match in pattern.finditer(html_text or ""):
        if len(reviews) >= max_reviews:
            break

        try:
            payload = json.loads(match.group(1))
        except Exception:
            continue

        text = sanitize_text(payload.get("message", ""))
        content_hash = compute_content_hash(text)
        if not text or content_hash in seen:
            continue

        try:
            rating = int(float(payload.get("productRating") or 0))
        except Exception:
            rating = 0

        review = create_review_record(len(reviews) + 1, text, rating)
        timestamp = str(payload.get("reviewCreateTime") or "")
        if timestamp.isdigit():
            review["date_scraped"] = datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
        review["source"] = "tokopedia_review_page"
        review["feedback_id"] = str(payload.get("feedbackID") or "")
        review["review_timestamp_label"] = str(payload.get("reviewCreateTimestamp") or "")

        is_valid, _ = validate_review(review)
        if is_valid:
            reviews.append(review)
            seen.add(content_hash)

    return reviews


def fetch_reviews_from_review_page(url: str, max_reviews: int) -> List[Dict]:
    """Fetch Tokopedia /review SSR page with Chrome impersonation and parse embedded reviews."""
    if curl_requests is None:
        logger.info("curl_cffi is not installed; skipping HTTP review-page fallback.")
        return []

    if "tk.tokopedia.com" in url.lower():
        try:
            resolved = curl_requests.get(
                normalize_url(url),
                impersonate="chrome124",
                timeout=20,
                allow_redirects=True,
                headers=DEFAULT_HTTP_HEADERS,
            )
            if resolved.url:
                url = normalize_url(resolved.url)
                logger.info("HTTP fallback resolved Tokopedia short link.")
        except Exception as exc:
            logger.warning(f"HTTP fallback short-link resolve failed: {exc}")

    review_url = build_review_page_url(url)
    try:
        logger.info(f"HTTP fallback: fetching review page {review_url[:90]}...")
        response = curl_requests.get(
            review_url,
            impersonate="chrome124",
            timeout=25,
            allow_redirects=True,
            headers=DEFAULT_HTTP_HEADERS,
        )
        if response.status_code >= 400:
            logger.warning(f"HTTP fallback review page returned status {response.status_code}")
            return []
    except Exception as exc:
        logger.warning(f"HTTP fallback review page failed: {exc}")
        return []

    reviews = extract_reviews_from_review_page_html(response.text, max_reviews)
    if reviews:
        logger.info(f"HTTP fallback extracted {len(reviews)} reviews from Tokopedia /review SSR cache.")
    else:
        logger.info("HTTP fallback found no embedded review rows.")
    return enrich_reviews_with_nlp(reviews)

# Cache configuration
CACHE_DIR = Path("scraper_cache")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_EXPIRY_HOURS = 24
DEFAULT_TARGET_URL = "https://www.tokopedia.com/klaten-bersinar/torso-memandikan-jenasah-jenazah-manusia-model-torso-jenazah"

class ScraperConfig:
    """Configuration untuk scraper"""
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 2  # seconds
    SCROLL_PAUSE_TIME = (0.5, 1.5)  # min, max
    SCROLL_ITERATIONS = 15
    ELEMENT_WAIT_TIMEOUT = 10000  # ms
    PAGE_LOAD_TIMEOUT = 25000  # ms
    DEFAULT_TIMEOUT = 15000  # ms
    NETWORK_QUIET_TIMEOUT = 8000  # ms
    RATE_LIMIT_DELAY = 2  # seconds between requests
    MAX_CONCURRENT_TASKS = 2
    MIN_REVIEW_TEXT_LENGTH = 5
    REVIEW_LOAD_TIMEOUT = 90
    HEADLESS = not can_launch_headed_browser()

config = ScraperConfig()

# ==========================================
# 1. DATA SANITIZATION & PREPROCESSING
# ==========================================
def sanitize_text(raw_text: str) -> str:
    """Membersihkan teks ulasan dari karakter tidak aman, newline, dan spasi berlebih."""
    if not raw_text:
        return ""
    # Remove HTML tags
    clean_text = re.sub(r'<.*?>', '', raw_text)
    # Remove emojis and special unicode characters (optional)
    clean_text = re.sub(r'[^\w\s\u0600-\u06FF\u3040-\u309F\u4E00-\u9FFF.!?,;:-]', '', clean_text)
    # Remove excessive newlines and carriage returns
    clean_text = clean_text.replace('\n', ' ').replace('\r', '')
    # Remove extra whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text)
    return clean_text.strip()

POSITIVE_WORDS = {
    "bagus", "baik", "mantap", "cepat", "puas", "memuaskan", "awet",
    "original", "ori", "oke", "ok", "sesuai", "murah", "rekomendasi",
    "recommended", "rapi", "aman", "suka", "terbaik", "keren",
    "berkualitas", "ramah", "berfungsi", "lancar", "kuat", "nyaman",
    "praktis", "sempurna", "top", "worth", "cepet", "tepat", "jernih",
    "halus", "solid", "lengkap", "terima", "kasih", "makasih"
}

NEGATIVE_WORDS = {
    "jelek", "rusak", "kecewa", "mengecewakan", "lambat", "palsu",
    "buruk", "cacat", "kurang", "parah", "mahal", "lama", "bohong",
    "pecah", "gagal", "komplain", "tipis", "lemah", "error", "macet",
    "retak", "lecet", "basah", "hancur", "telat", "terlambat", "batal",
    "tipu", "zonk", "hilang", "salah", "kosong", "kotor", "penyok",
    "sobek", "reject", "minus", "bermasalah"
}

NEGATIONS = {"tidak", "tak", "bukan", "ga", "gak", "nggak", "enggak", "belum"}
INTENSIFIERS = {"sangat", "banget", "sekali", "amat", "super", "parah", "bener", "benar"}

POSITIVE_PHRASES = {
    "sesuai deskripsi": 2.0,
    "pengiriman cepat": 2.0,
    "barang sampai": 1.0,
    "packing aman": 2.0,
    "kualitas bagus": 2.0,
    "harga murah": 1.5,
    "berfungsi dengan baik": 2.0,
    "terima kasih": 1.0,
    "recommended seller": 2.0,
}

NEGATIVE_PHRASES = {
    "tidak sesuai": -2.0,
    "gak sesuai": -2.0,
    "nggak sesuai": -2.0,
    "barang rusak": -2.5,
    "barang cacat": -2.5,
    "pengiriman lama": -2.0,
    "tidak berfungsi": -2.5,
    "kurang bagus": -2.0,
    "kecewa banget": -2.0,
    "tidak original": -2.5,
    "barang palsu": -3.0,
    "salah kirim": -2.0,
    "barang tidak sampai": -3.0,
}

NEUTRAL_PHRASES = {"biasa saja", "standar saja", "lumayan saja", "cukup saja"}

REVIEW_NOISE_PATTERNS = [
    r'^\d+\s+pembeli\s+merasa\s+puas$',
    r'^\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+.*\brating\b.*\bulasan\b.*$',
    r'^diambil\s+dari\s+tokopedia',
    r'tiktok\s+shop\s+by\s+tokopedia',
    r'^belum\s+ada\s+ulasan',
    r'^lihat\s+semua\s+ulasan',
    r'^tulis\s+ulasan',
    r'^\d+\s+rating\b',
    r'^\d+\s+ulasan\b',
]

INDONESIAN_STOPWORDS = {
    "ada", "adalah", "agar", "akan", "aku", "anda", "atau", "bagaimana",
    "bagi", "bahwa", "banyak", "baru", "begini", "begitu", "belum", "bisa",
    "buat", "dalam", "dan", "dapat", "dari", "daripada", "dengan", "di",
    "dia", "ini", "itu", "jadi", "jangan", "jika", "juga", "karena",
    "kami", "kamu", "kan", "ke", "kembali", "kemudian", "kepada", "kita",
    "lagi", "lah", "lain", "lalu", "lebih", "maka", "masih", "mereka",
    "nya", "oleh", "pada", "paling", "para", "per", "saat", "saja",
    "saling", "sama", "sangat", "saya", "sebagai", "sebelum", "sebuah",
    "sedang", "sehingga", "sekali", "semua", "sendiri", "seperti", "serta",
    "si", "sudah", "supaya", "tapi", "telah", "tentang", "tersebut",
    "tetapi", "tidak", "untuk", "yang", "ya", "yaitu", "yakni",
    "aja", "banget", "dong", "nih", "sih", "kok", "deh"
}

IRREGULAR_STEMS = {
    "barangnya": "barang",
    "produknya": "produk",
    "paketnya": "paket",
    "packingnya": "packing",
    "sellernya": "seller",
    "tokonya": "toko",
    "pengiriman": "kirim",
    "dikirim": "kirim",
    "terkirim": "kirim",
    "mengirim": "kirim",
    "kiriman": "kirim",
    "berfungsi": "fungsi",
    "memuaskan": "puas",
    "mengecewakan": "kecewa",
    "digunakan": "guna",
    "menggunakan": "guna",
    "pemakaian": "pakai",
    "sesuai": "sesuai",
}

NLP_VECTOR_MAX_FEATURES = 25
NLP_VECTOR_PREFIX = "vec_"

def tokenize_text(text: str) -> List[str]:
    """Tokenisasi ringan untuk ulasan Bahasa Indonesia."""
    tokens = re.findall(r'[a-z0-9]+', text.lower())
    return [re.sub(r'(.)\1{2,}', r'\1\1', token) for token in tokens]

def remove_stopwords(tokens: List[str]) -> List[str]:
    """Hapus stopword umum agar kata bermakna lebih dominan."""
    return [
        token for token in tokens
        if (token not in INDONESIAN_STOPWORDS or token in NEGATIONS) and len(token) > 1
    ]

def stem_indonesian_word(word: str) -> str:
    """Stemmer ringan Bahasa Indonesia tanpa dependency eksternal."""
    token = str(word or "").lower().strip()
    if len(token) <= 3:
        return token

    if token in IRREGULAR_STEMS:
        return IRREGULAR_STEMS[token]

    for suffix in ("lah", "kah", "tah", "pun"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[:-len(suffix)]
            break

    for suffix in ("ku", "mu", "nya"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[:-len(suffix)]
            break

    if token in IRREGULAR_STEMS:
        return IRREGULAR_STEMS[token]

    prefix_rules = [
        ("meny", "s"), ("peny", "s"),
        ("meng", ""), ("peng", ""),
        ("mem", ""), ("pem", ""),
        ("men", ""), ("pen", ""),
        ("ber", ""), ("ter", ""),
        ("per", ""), ("di", ""),
        ("ke", ""), ("se", ""),
        ("me", ""), ("pe", ""),
    ]
    for prefix, replacement in prefix_rules:
        if token.startswith(prefix) and len(token) - len(prefix) >= 4:
            token = replacement + token[len(prefix):]
            break

    for suffix in ("kan", "an", "i"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[:-len(suffix)]
            break

    return IRREGULAR_STEMS.get(token, token)

def stem_tokens(tokens: List[str]) -> List[str]:
    """Ubah token hasil stopword removal menjadi bentuk dasar sederhana."""
    return [stem_indonesian_word(token) for token in tokens if token]

def build_nlp_features(text: str) -> Dict:
    """Bangun tahapan NLP per ulasan: tokenization, stopword removal, stemming."""
    tokens = tokenize_text(sanitize_text(text))
    tokens_no_stopwords = remove_stopwords(tokens)
    stemmed_tokens = stem_tokens(tokens_no_stopwords)
    term_frequency = dict(Counter(stemmed_tokens))

    return {
        "nlp_tokens": tokens,
        "nlp_no_stopwords": tokens_no_stopwords,
        "nlp_stems": stemmed_tokens,
        "nlp_term_frequency": term_frequency,
    }

def _vector_column_name(term: str, used_columns: set) -> str:
    base = re.sub(r'[^a-z0-9]+', '_', str(term).lower()).strip('_') or "term"
    column = f"{NLP_VECTOR_PREFIX}{base}"
    if column not in used_columns:
        used_columns.add(column)
        return column

    counter = 2
    while f"{column}_{counter}" in used_columns:
        counter += 1
    column = f"{column}_{counter}"
    used_columns.add(column)
    return column

def enrich_reviews_with_nlp(data: List[Dict], max_features: int = NLP_VECTOR_MAX_FEATURES) -> List[Dict]:
    """Tambahkan fitur NLP dan vectorization ke semua review dalam satu corpus."""
    if not data:
        return data

    corpus_counts = Counter()
    for review in data:
        if not isinstance(review, dict):
            continue

        for key in list(review.keys()):
            if str(key).startswith(NLP_VECTOR_PREFIX):
                del review[key]

        features = build_nlp_features(review.get("review_text", ""))
        review.update(features)
        corpus_counts.update(features["nlp_stems"])

    vocabulary = [
        term for term, _ in corpus_counts.most_common(max_features)
        if term and not term.isdigit()
    ]

    used_columns = set()
    vector_columns = [_vector_column_name(term, used_columns) for term in vocabulary]

    for review in data:
        if not isinstance(review, dict):
            continue

        term_counts = Counter(review.get("nlp_stems", []))
        vector_values = [int(term_counts.get(term, 0)) for term in vocabulary]
        review["vector_terms"] = vocabulary
        review["vector_values"] = vector_values

        for column, value in zip(vector_columns, vector_values):
            review[column] = value

    return data

def create_review_record(review_id: int, text: str, rating: int) -> Dict:
    """Buat object review lengkap dengan fitur NLP."""
    safe_text = sanitize_text(text)
    review_obj = {
        "id": review_id,
        "review_text": safe_text,
        "rating": rating,
        "sentiment": analyze_sentiment(safe_text),
        "date_scraped": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "text_length": len(safe_text),
        "source": "tokopedia"
    }
    review_obj.update(build_nlp_features(safe_text))
    return review_obj

def is_probably_review_text(text: str) -> bool:
    """Filter agar teks ringkasan/rating halaman tidak masuk sebagai ulasan."""
    clean_text = sanitize_text(text)
    if len(clean_text) < config.MIN_REVIEW_TEXT_LENGTH:
        return False

    lower = clean_text.lower()
    for pattern in REVIEW_NOISE_PATTERNS:
        if re.search(pattern, lower):
            return False

    tokens = tokenize_text(lower)
    if len(tokens) < 2 and lower not in POSITIVE_WORDS and lower not in NEGATIVE_WORDS:
        return False

    digit_count = sum(ch.isdigit() for ch in lower)
    if digit_count / max(len(lower), 1) > 0.35:
        return False

    summary_terms = [
        "rating", "ulasan", "pembeli merasa puas", "terjual", "diskusi",
        "diambil dari tokopedia", "tiktok shop"
    ]
    if sum(1 for term in summary_terms if term in lower) >= 2:
        return False

    return True

def extract_rating(rating_text: str) -> int:
    """Extract rating dari teks rating dengan validation."""
    if not rating_text:
        return 0
    try:
        # Cari angka di dalam teks (e.g., "5" atau "5.0")
        match = re.search(r'(\d+(?:\.\d+)?)', rating_text.strip())
        if match:
            rating = int(float(match.group(1)))
            # Validate rating range (1-5)
            return max(1, min(5, rating))
        return 0
    except:
        return 0

def analyze_sentiment(text: str) -> str:
    """Analisis sentimen ulasan Indonesia dengan lexicon dan fallback TextBlob."""
    if not text or len(text) < 3:
        return "neutral"

    clean_text = sanitize_text(text).lower()
    tokens = tokenize_text(clean_text)
    score = 0.0

    for phrase, value in POSITIVE_PHRASES.items():
        if phrase in clean_text:
            score += value

    for phrase, value in NEGATIVE_PHRASES.items():
        if phrase in clean_text:
            score += value

    for index, token in enumerate(tokens):
        token_score = 0.0
        if token in POSITIVE_WORDS:
            token_score = 1.0
        elif token in NEGATIVE_WORDS:
            token_score = -1.0

        if token_score == 0:
            continue

        previous_tokens = tokens[max(0, index - 2):index]
        if any(prev in NEGATIONS for prev in previous_tokens):
            token_score *= -1

        if any(prev in INTENSIFIERS for prev in previous_tokens) or (
            index + 1 < len(tokens) and tokens[index + 1] in INTENSIFIERS
        ):
            token_score *= 1.5

        score += token_score

    if any(phrase in clean_text for phrase in NEUTRAL_PHRASES) and abs(score) <= 1.5:
        return "neutral"

    if score >= 1.0:
        return "positive"
    if score <= -1.0:
        return "negative"

    try:
        blob = TextBlob(clean_text)
        polarity = blob.sentiment.polarity
        
        if polarity > 0.10:
            return "positive"
        elif polarity < -0.10:
            return "negative"
    except Exception as e:
        logger.warning(f"Sentiment analysis error: {e}")

    return "neutral"

def compute_content_hash(text: str) -> str:
    """Compute hash dari konten untuk deduplicasi yang lebih akurat."""
    normalized = re.sub(r'\s+', ' ', sanitize_text(text).lower()).strip()
    return hashlib.md5(normalized.encode()).hexdigest()

def validate_review(review_data: Dict) -> Tuple[bool, str]:
    """Validate extracted review data."""
    text = review_data.get('review_text', '').strip()
    
    if not is_probably_review_text(text):
        return False, "Text is too short or looks like page summary/noise"
    
    # Check for valid sentiment
    if review_data.get('sentiment') not in ['positive', 'negative', 'neutral']:
        return False, "Invalid sentiment"
    
    # Check rating range
    rating = review_data.get('rating', 0)
    if not (0 <= rating <= 5):
        return False, f"Invalid rating: {rating}"
    
    return True, "Valid"

def score_review_candidate(text: str) -> float:
    """Skor kandidat teks agar elemen ulasan murni diprioritaskan."""
    lower = text.lower()
    score = float(len(text))
    if len(text) > 600:
        score -= 200
    if any(term in lower for term in ["rating", "ulasan", "pembeli merasa puas", "terjual"]):
        score -= 100
    if any(word in lower for word in POSITIVE_WORDS | NEGATIVE_WORDS):
        score += 50
    if any(term in lower for term in ["produk", "barang", "seller", "pengiriman", "packing", "paket", "sesuai"]):
        score += 20
    return score

def is_strong_review_candidate(text: str) -> bool:
    """Filter tambahan untuk fallback teks halaman agar tidak mengambil deskripsi produk."""
    if not is_probably_review_text(text):
        return False

    lower = text.lower()
    tokens = tokenize_text(lower)
    if len(tokens) > 80:
        return False

    review_terms = {
        "produk", "barang", "seller", "penjual", "pengiriman", "packing",
        "paket", "sesuai", "mantap", "bagus", "cepat", "puas", "rusak",
        "kecewa", "ori", "original", "aman", "rapi", "recommended"
    }
    if any(term in tokens for term in review_terms):
        return True

    return any(phrase in lower for phrase in POSITIVE_PHRASES) or any(phrase in lower for phrase in NEGATIVE_PHRASES)

async def extract_review_text_from_element(element) -> str:
    """Ambil teks ulasan dari elemen/card dan buang metadata halaman."""
    candidates = []
    seen = set()

    async def add_candidate(raw_text: str):
        for segment in str(raw_text or "").splitlines():
            clean_segment = sanitize_text(segment)
            if not clean_segment:
                continue
            content_hash = compute_content_hash(clean_segment)
            if content_hash in seen:
                continue
            seen.add(content_hash)
            if is_probably_review_text(clean_segment):
                candidates.append(clean_segment)

    try:
        await add_candidate(await element.inner_text())
    except:
        pass

    child_selectors = [
        'span[data-testid="lblItemUlasan"]',
        '[data-testid*="lblItemUlasan"]',
        '[data-testid*="reviewContent"]',
        '[data-testid*="review-content"]',
        '[class*="review"]',
        '[class*="Review"]',
        '[class*="ulasan"]',
        'p',
        'span',
    ]

    for selector in child_selectors:
        try:
            children = await element.query_selector_all(selector)
            for child in children:
                await add_candidate(await child.inner_text())
        except:
            continue

    if not candidates:
        return ""

    return max(candidates, key=score_review_candidate)

async def extract_rating_from_element(element) -> int:
    """Ambil rating jika ada. Return 0 saat tidak ditemukan agar tidak bias."""
    rating_selectors = [
        '[aria-label*="bintang"]',
        '[aria-label*="Bintang"]',
        '[aria-label*="star"]',
        '[aria-label*="Star"]',
        '[class*="rating"]',
        '[class*="Rating"]',
        '[data-testid*="rating"]',
        '[data-testid*="Rating"]',
    ]

    for selector in rating_selectors:
        try:
            elements = await element.query_selector_all(selector)
            for rating_elem in elements:
                for attribute in ["aria-label", "title", "alt"]:
                    value = await rating_elem.get_attribute(attribute)
                    rating = extract_rating(value or "")
                    if rating:
                        return rating

                rating_text = await rating_elem.inner_text()
                rating = extract_rating(rating_text)
                if rating:
                    return rating
        except:
            continue

    return 0

async def open_review_section(page) -> bool:
    """Coba buka tab/modal/section ulasan sebelum ekstraksi."""
    clicked_any = False
    click_result = None

    try:
        click_result = await page.evaluate("""
            () => {
                const include = ['lihat semua ulasan', 'semua ulasan', 'ulasan pembeli', 'ulasan'];
                const exclude = ['tulis ulasan', 'beri ulasan', 'diskusi'];
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style && style.visibility !== 'hidden' && style.display !== 'none' &&
                        rect.width > 0 && rect.height > 0;
                };
                const nodes = Array.from(document.querySelectorAll('button, a, [role="button"], div, span'));
                for (const node of nodes) {
                    const text = (node.innerText || node.textContent || '').trim().toLowerCase();
                    if (!text || text.length > 120 || !visible(node)) continue;
                    if (!include.some(keyword => text.includes(keyword))) continue;
                    if (exclude.some(keyword => text.includes(keyword))) continue;

                    const clickable = node.closest('button, a, [role="button"]') || node;
                    clickable.scrollIntoView({block: 'center', inline: 'center'});
                    clickable.click();
                    return text.slice(0, 100);
                }
                return null;
            }
        """)
    except Exception as e:
        logger.debug(f"Review section click evaluation failed: {str(e)[:80]}")

    if click_result:
        logger.info(f"Opened review section via text: {click_result}")
        clicked_any = True
        await asyncio.sleep(2)

    # Scroll menuju heading ulasan jika ada.
    try:
        found_heading = await page.evaluate("""
            () => {
                const nodes = Array.from(document.querySelectorAll('h1,h2,h3,h4,section,div,span'));
                const target = nodes.find(node => {
                    const text = (node.innerText || node.textContent || '').trim().toLowerCase();
                    return text && text.length < 80 && (text.includes('ulasan') || text.includes('review'));
                });
                if (target) {
                    target.scrollIntoView({block: 'center', inline: 'center'});
                    return (target.innerText || target.textContent || '').trim().slice(0, 80);
                }
                return null;
            }
        """)
        if found_heading:
            logger.info(f"Scrolled to possible review section: {found_heading}")
            await asyncio.sleep(1)
    except Exception as e:
        logger.debug(f"Review section scroll failed: {str(e)[:80]}")

    # Trigger lazy rendering di area ulasan.
    for _ in range(5):
        await page.mouse.wheel(0, 700)
        await asyncio.sleep(random.uniform(0.5, 1.0))

    return clicked_any

async def trigger_review_lazy_load(page):
    """Fokuskan ulang viewport ke area ulasan agar skeleton/card review ikut dimuat."""
    try:
        await page.evaluate("""
            () => {
                const nodes = Array.from(document.querySelectorAll('h1,h2,h3,h4,section,div,span'));
                const target = nodes.find(node => {
                    const text = (node.innerText || node.textContent || '').trim().toLowerCase();
                    return text && text.length < 100 &&
                        (text.includes('ulasan pembeli') || text === 'ulasan' || text.includes('review'));
                });
                if (target) {
                    target.scrollIntoView({block: 'center', inline: 'center'});
                }
            }
        """)
    except Exception:
        pass

    for delta in (500, -160, 700):
        try:
            await page.mouse.wheel(0, delta)
            await asyncio.sleep(0.5)
        except Exception:
            break

async def extract_review_text_candidates_from_page(page, max_candidates: int = 200) -> List[str]:
    """Fallback: ambil kandidat ulasan dari teks terlihat di halaman."""
    try:
        raw_candidates = await page.evaluate("""
            () => {
                const selectors = [
                    '[data-testid*="ulasan"]',
                    '[data-testid*="review"]',
                    '[class*="review"]',
                    '[class*="Review"]',
                    '[class*="ulasan"]',
                    'article',
                    'p',
                    'span',
                    'div'
                ];
                const values = [];
                const seen = new Set();
                for (const selector of selectors) {
                    for (const node of Array.from(document.querySelectorAll(selector))) {
                        const style = window.getComputedStyle(node);
                        const rect = node.getBoundingClientRect();
                        if (!style || style.visibility === 'hidden' || style.display === 'none') continue;
                        if (rect.width <= 0 || rect.height <= 0) continue;

                        const text = (node.innerText || node.textContent || '').trim();
                        if (!text || text.length < 5 || text.length > 700) continue;

                        for (const part of text.split(/\\n+/)) {
                            const clean = part.replace(/\\s+/g, ' ').trim();
                            if (clean.length < 5 || clean.length > 500) continue;
                            const key = clean.toLowerCase();
                            if (seen.has(key)) continue;
                            seen.add(key);
                            values.push(clean);
                        }
                    }
                }
                return values.slice(0, 500);
            }
        """)
    except Exception as e:
        logger.debug(f"Page text fallback extraction failed: {str(e)[:80]}")
        return []

    unique_candidates = {}
    for raw_text in raw_candidates:
        clean_text = sanitize_text(raw_text)
        if is_strong_review_candidate(clean_text):
            unique_candidates[compute_content_hash(clean_text)] = clean_text

    candidates = sorted(unique_candidates.values(), key=score_review_candidate, reverse=True)
    return candidates[:max_candidates]

async def get_review_loading_state(page) -> Dict:
    """Ambil status loading section ulasan untuk menghindari ekstraksi terlalu cepat."""
    try:
        return await page.evaluate("""
            () => {
                const text = document.body ? document.body.innerText : '';
                const lower = text.toLowerCase();
                const skeletonSelectors = [
                    '[class*="skeleton"]',
                    '[class*="Skeleton"]',
                    '[aria-busy="true"]',
                    '[data-testid*="skeleton"]',
                    '[data-testid*="loading"]'
                ];
                let skeletonCount = 0;
                for (const selector of skeletonSelectors) {
                    for (const node of document.querySelectorAll(selector)) {
                        const style = window.getComputedStyle(node);
                        const rect = node.getBoundingClientRect();
                        if (style && style.display !== 'none' && style.visibility !== 'hidden' &&
                            rect.width > 0 && rect.height > 0) {
                            skeletonCount += 1;
                        }
                    }
                }
                return {
                    textLength: text.length,
                    hasReviewSummary: lower.includes('ulasan pembeli') || lower.includes('rating') || lower.includes('ulasan'),
                    hasNoReviewText: lower.includes('belum ada ulasan'),
                    skeletonCount
                };
            }
        """)
    except Exception:
        return {"textLength": 0, "hasReviewSummary": False, "hasNoReviewText": False, "skeletonCount": 0}

async def wait_for_review_content(page, network_review_candidates: Dict, timeout_seconds: int) -> bool:
    """Tunggu sampai ulasan selesai loading atau kandidat ulasan/API muncul."""
    logger.info(f"Waiting for review content up to {timeout_seconds}s...")
    deadline = time.time() + timeout_seconds
    last_log_second = 0
    last_trigger_second = 0
    reload_attempted = False

    while time.time() < deadline:
        if network_review_candidates:
            logger.info(f"Review API data detected: {len(network_review_candidates)} candidates")
            return True

        candidates = await extract_review_text_candidates_from_page(page, max_candidates=5)
        if candidates:
            logger.info(f"Visible review text detected: {len(candidates)} candidates")
            return True

        state = await get_review_loading_state(page)
        elapsed = int(timeout_seconds - (deadline - time.time()))

        if elapsed - last_trigger_second >= 12:
            await trigger_review_lazy_load(page)
            last_trigger_second = elapsed

        if (
            not reload_attempted
            and elapsed >= 35
            and state.get("skeletonCount", 0) > 0
            and not network_review_candidates
        ):
            reload_attempted = True
            logger.warning("Review cards masih loading. Reload halaman sekali lalu coba buka area ulasan lagi...")
            try:
                await page.reload(wait_until="domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT)
                await asyncio.sleep(5)
                await open_review_section(page)
            except Exception as e:
                logger.debug(f"Review reload attempt failed: {str(e)[:80]}")

        if elapsed - last_log_second >= 10:
            logger.info(
                f"Still waiting for reviews... skeleton={state.get('skeletonCount', 0)}, "
                f"text={state.get('textLength', 0)} chars"
            )
            last_log_second = elapsed

        await page.mouse.wheel(0, 500)
        await asyncio.sleep(2)

    state = await get_review_loading_state(page)
    logger.warning(
        f"Review content timeout. skeleton={state.get('skeletonCount', 0)}, "
        f"text={state.get('textLength', 0)} chars"
    )
    return False

async def save_debug_snapshot(page, reason: str):
    """Simpan snapshot debug saat scraper tidak menemukan ulasan."""
    safe_reason = re.sub(r'[^a-z0-9_]+', '_', reason.lower()).strip('_') or 'debug'
    try:
        await page.screenshot(path=f"debug_{safe_reason}.png", full_page=True)
    except Exception:
        pass
    try:
        with open(f"debug_{safe_reason}.html", "w", encoding="utf-8") as f:
            f.write(await page.content())
    except Exception:
        pass
    try:
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        with open(f"debug_{safe_reason}.txt", "w", encoding="utf-8") as f:
            f.write(text or "")
    except Exception:
        pass

def extract_review_candidates_from_json(data) -> List[Tuple[str, int]]:
    """Ambil kandidat ulasan dari response JSON/API secara generik."""
    text_keys = {
        "review", "reviewtext", "review_text", "content", "comment",
        "message", "text", "description", "ulasan", "feedback"
    }
    rating_keys = {"rating", "rate", "score", "star", "stars"}
    results = []

    def walk(node, inherited_rating: int = 0):
        if isinstance(node, dict):
            local_rating = inherited_rating
            text_values = []

            for key, value in node.items():
                key_norm = re.sub(r'[^a-z]', '', str(key).lower())

                if key_norm in rating_keys:
                    local_rating = extract_rating(str(value))

                if isinstance(value, str):
                    clean_value = sanitize_text(value)
                    if key_norm in text_keys or is_strong_review_candidate(clean_value):
                        if is_strong_review_candidate(clean_value):
                            text_values.append(clean_value)

            for text_value in text_values:
                results.append((text_value, local_rating))

            for value in node.values():
                walk(value, local_rating)

        elif isinstance(node, list):
            for item in node:
                walk(item, inherited_rating)

    walk(data)

    unique = {}
    for text, rating in results:
        unique[compute_content_hash(text)] = (text, rating)

    return list(unique.values())

# ==========================================
# 2. CACHE MANAGEMENT
# ==========================================
def get_cache_file(url: str) -> Path:
    """Generate cache filename dari URL."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    return CACHE_DIR / f"cache_{url_hash}.json"

def is_cache_valid(cache_file: Path) -> bool:
    """Check if cache file masih valid (tidak expired)."""
    if not cache_file.exists():
        return False
    
    file_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
    return file_age < timedelta(hours=CACHE_EXPIRY_HOURS)

def load_from_cache(url: str) -> Optional[List[Dict]]:
    """Load reviews dari cache jika tersedia dan valid."""
    cache_file = get_cache_file(url)
    
    if is_cache_valid(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"✓ Loaded {len(data)} reviews dari cache")
                valid_data = [item for item in data if validate_review(item)[0]]
                if not valid_data:
                    logger.info("Cache ignored because it contains no valid review text")
                    return None
                if len(valid_data) != len(data):
                    logger.info(f"Cache filtered: {len(valid_data)}/{len(data)} valid reviews")
                return enrich_reviews_with_nlp(valid_data)
        except Exception as e:
            logger.warning(f"Cache loading error: {e}")
    
    return None

def save_to_cache(url: str, data: List[Dict]):
    """Save reviews ke cache."""
    cache_file = get_cache_file(url)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"✓ Cache saved: {cache_file}")
    except Exception as e:
        logger.warning(f"Cache save error: {e}")

# ==========================================
# 3. INTELLIGENT SCROLL DETECTION
# ==========================================
async def detect_lazy_loading(page) -> bool:
    """Detect if page memiliki lazy loading mechanism."""
    try:
        # Check untuk intersection observer, scroll event listeners, atau data-attributes
        lazy_indicators = await page.evaluate("""
            () => {
                // Check untuk common lazy-load patterns
                const hasIntersectionObserver = 'IntersectionObserver' in window;
                const hasLazyElements = document.querySelectorAll('[data-lazy], [loading="lazy"]').length > 0;
                const hasDynamicLoading = !!window.LazyLoadJS || !!window.LazyLoad;
                
                return {
                    hasIntersectionObserver,
                    hasLazyElements,
                    hasDynamicLoading
                };
            }
        """)
        
        has_lazy = any(lazy_indicators.values())
        if has_lazy:
            logger.info("✓ Detected lazy-loading mechanism")
        return has_lazy
    except:
        return False

async def wait_for_new_content(page, last_height: int, timeout_ms: int = 5000) -> Tuple[bool, int]:
    """Wait untuk konten baru setelah scroll dengan intelligent timeout."""
    try:
        start_time = time.time()
        while (time.time() - start_time) * 1000 < timeout_ms:
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height > last_height:
                logger.info(f"✓ New content detected: {last_height} -> {new_height}px")
                return True, new_height
            await asyncio.sleep(0.2)
        
        return False, last_height
    except:
        return False, last_height


async def wait_for_review_network_quiet(network_review_candidates: Dict, timeout_ms: int) -> int:
    """Wait until no new review candidates arrive for a short window."""
    start = time.time()
    last_count = len(network_review_candidates)
    last_change = start

    while (time.time() - start) * 1000 < timeout_ms:
        await asyncio.sleep(0.5)
        current_count = len(network_review_candidates)
        if current_count != last_count:
            last_count = current_count
            last_change = time.time()

        if current_count > 0 and (time.time() - last_change) >= 1.5:
            return current_count

    return len(network_review_candidates)


async def navigate_product_page(page, url: str) -> bool:
    """Navigate with a fast dynamic-page strategy and a commit fallback."""
    if "tokopedia.com" in url.lower():
        try:
            await asyncio.wait_for(
                page.goto(url, wait_until="commit", timeout=15000),
                timeout=20,
            )
            logger.info("✓ Page navigation committed")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                logger.info("✓ Page DOM content loaded after commit")
                return True
            except PlaywrightTimeoutError:
                logger.warning("⚠️ DOMContentLoaded still pending after commit, continuing with committed page.")
                return False
        except Exception as exc:
            logger.warning(f"Commit-first navigation failed: {exc}")
            raise

    try:
        await asyncio.wait_for(
            page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT),
            timeout=(config.PAGE_LOAD_TIMEOUT / 1000) + 5,
        )
        logger.info("✓ Page DOM content loaded")
        return True
    except (asyncio.TimeoutError, PlaywrightTimeoutError):
        logger.warning("⚠️ DOMContentLoaded timeout, checking committed document state...")
        if page.url and page.url != "about:blank":
            return False

        try:
            await asyncio.wait_for(
                page.goto(url, wait_until="commit", timeout=10000),
                timeout=15,
            )
            logger.info("✓ Page navigation committed")
            return False
        except Exception as exc:
            logger.warning(f"Commit fallback failed: {exc}")
            raise

# ==========================================
# 4. ADVANCED SCRAPING WITH RETRY LOGIC
# ==========================================
async def scrape_reviews_advanced(
    url: str,
    max_reviews: int = 100,
    use_cache: bool = True,
    retry_count: int = 0,
    headless: Optional[bool] = None
) -> list:
    """
    Scrape reviews dengan smart scrolling, retry logic, dan caching.
    
    Features:
    - Automatic cache checking untuk menghindari scrape ulang
    - Intelligent lazy-load detection
    - Adaptive retry logic dengan exponential backoff
    - Better error recovery dan validation
    - Rate limiting untuk respect server
    """
    url = resolve_short_url(url)
    
    # Check cache terlebih dahulu
    if use_cache:
        cached_data = load_from_cache(url)
        if cached_data:
            return cached_data

    http_reviews = fetch_reviews_from_review_page(url, max_reviews)
    if http_reviews:
        if use_cache:
            save_to_cache(url, http_reviews)
        return http_reviews
    
    # Rate limiting
    if retry_count > 0:
        delay = config.RETRY_DELAY_BASE ** retry_count
        logger.info(f"⏳ Rate limiting delay: {delay}s (retry {retry_count})")
        await asyncio.sleep(min(delay, 30))  # Cap maksimal 30 detik
    
    reviews_data = []
    reviews_hash_set = set()  # Untuk deduplicasi yang lebih akurat
    effective_headless = config.HEADLESS if headless is None else headless
    if not effective_headless and not can_launch_headed_browser():
        logger.warning("Browser visual diminta, tetapi XServer/DISPLAY tidak tersedia. Menggunakan mode headless.")
        effective_headless = True
    
    async with async_playwright() as p:
        browser = None
        try:
            logger.info(f"🌐 Starting scraper untuk: {url[:60]}...")
            
            browser = await p.chromium.launch(
                headless=effective_headless,
                args=[
                    "--disable-http2",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1366, 'height': 768},
                user_agent=DESKTOP_USER_AGENT,
                locale="id-ID",
                timezone_id="Asia/Jakarta",
                extra_http_headers=DEFAULT_HTTP_HEADERS,
                service_workers="block",
            )
            context.set_default_timeout(config.DEFAULT_TIMEOUT)
            context.set_default_navigation_timeout(config.PAGE_LOAD_TIMEOUT)
            page = await context.new_page()
            network_review_candidates = {}
            review_response_urls = set()

            async def collect_review_response(response):
                try:
                    url_lower = response.url.lower()
                    if not any(keyword in url_lower for keyword in ["review", "ulasan", "graphql", "pdp", "rating"]):
                        return

                    content_type = response.headers.get("content-type", "").lower()
                    if "json" not in content_type and "graphql" not in url_lower:
                        return

                    data = await response.json()
                    before_count = len(network_review_candidates)
                    for text, rating in extract_review_candidates_from_json(data):
                        network_review_candidates[compute_content_hash(text)] = (text, rating)
                    if len(network_review_candidates) > before_count:
                        review_response_urls.add(response.url)
                except Exception:
                    return

            page.on("response", lambda response: asyncio.create_task(collect_review_response(response)))

            # Aktifkan stealth mode untuk bypass bot detection
            stealth = Stealth()
            await stealth.apply_stealth_async(context)
            await stealth.apply_stealth_async(page)

            logger.info(f"📄 Loading page...")
            
            # Page load dengan timeout adaptif
            try:
                await navigate_product_page(page, url)
            except Exception as e:
                logger.error(f"❌ Page load error: {e}")
                raise
            
            # Wait untuk konten dirender
            await asyncio.sleep(3)
            network_count = await wait_for_review_network_quiet(
                network_review_candidates,
                config.NETWORK_QUIET_TIMEOUT
            )
            if network_count:
                logger.info(
                    f"Network capture collected {network_count} review candidates "
                    f"from {len(review_response_urls)} response(s)."
                )
            
            # Detect lazy loading
            has_lazy = await detect_lazy_loading(page)
            
            # ===== INTELLIGENT INFINITE SCROLLING =====
            logger.info("📜 Starting intelligent scroll...")
            
            last_height = await page.evaluate("document.body.scrollHeight")
            scroll_count = 0
            no_new_content_count = 0
            max_scroll_iterations = config.SCROLL_ITERATIONS if has_lazy else 8
            
            while scroll_count < max_scroll_iterations and no_new_content_count < 3:
                # Scroll ke bawah dengan smooth motion
                await page.evaluate("window.scrollBy(0, 800)")
                await asyncio.sleep(random.uniform(*config.SCROLL_PAUSE_TIME))
                
                # Check untuk konten baru
                new_content_found, new_height = await wait_for_new_content(page, last_height)
                
                if not new_content_found:
                    no_new_content_count += 1
                    logger.info(f"⏸️  No new content ({no_new_content_count}/3)")
                else:
                    no_new_content_count = 0
                
                last_height = new_height
                scroll_count += 1
                logger.info(f"📊 Scroll {scroll_count}/{max_scroll_iterations}: {new_height}px")
                
                # Tunggu lazy loading dengan adaptive timing
                await asyncio.sleep(random.uniform(0.3, 0.8))
            
            logger.info("✓ Scrolling complete")
            await open_review_section(page)
            review_content_ready = await wait_for_review_content(
                page,
                network_review_candidates,
                config.REVIEW_LOAD_TIMEOUT
            )
            if not review_content_ready:
                logger.warning(
                    "Ulasan belum terbuka atau masih loading. Scraper akan mencoba fallback dan menyimpan debug jika tetap kosong."
                )
            logger.info("🔍 Starting review extraction...")

            # ===== ENHANCED SELECTOR STRATEGY =====
            review_selectors = [
                # Tokopedia specific selectors
                'span[data-testid*="lblItemUlasan"]',
                'span[data-testid="lblItemUlasan"]',
                '[data-testid*="reviewContent"]',
                '[data-testid*="review-content"]',
                '[data-testid*="Review"]',
                '[data-testid*="ReviewCard"]',
                '[data-testid*="cardReview"]',
                '[data-testid*="ulasan"]',
                '[data-testid*="review"]',
                'div:has(span[data-testid*="lblItemUlasan"])',
                'div:has(p[data-testid*="lblItemUlasan"])',
                
                # Generic review patterns
                'p[class*="review"]',
                'span[class*="review"]',
                'div[class*="review"]',
                'div[class*="Review"]',
                'div[class*="feedback"]',
                
                # Indonesian e-commerce specific
                'div[class*="UlasanPenjual"]',
                'div[class*="ProductReview"]',
                'div[class*="ulasan"]',
                
                # Fallback selectors
                'div[role="article"]',
                'article',
                '.review-card',
                '.feedback-item'
            ]
            
            all_review_elements = []
            successful_selectors = []
            
            for selector in review_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if len(elements) > 0:
                        # Filter elemen yang tidak kosong
                        valid_elements = []
                        for elem in elements:
                            try:
                                text = await extract_review_text_from_element(elem)
                                if text:
                                    valid_elements.append(elem)
                            except:
                                continue
                        
                        if len(valid_elements) > 0:
                            logger.info(f"✓ Selector '{selector}' found {len(valid_elements)} reviews")
                            all_review_elements.extend(valid_elements)
                            successful_selectors.append(selector)
                except Exception as e:
                    logger.debug(f"Selector '{selector}' failed: {str(e)[:50]}")
                    continue
            
            logger.info(f"📊 Found {len(all_review_elements)} elements from {len(successful_selectors)} selectors")
            
            # ===== SMART DEDUPLICATION =====
            unique_reviews = {}
            for elem in all_review_elements:
                try:
                    text = await extract_review_text_from_element(elem)
                    if text:
                        content_hash = compute_content_hash(text)
                        if content_hash not in unique_reviews:
                            unique_reviews[content_hash] = elem
                except:
                    continue
            
            all_review_elements = list(unique_reviews.values())
            logger.info(f"🔄 Deduplicated to {len(all_review_elements)} unique reviews")
            
            # ===== EXTRACT REVIEW DETAILS WITH VALIDATION =====
            extracted_count = 0
            skipped_count = 0

            if network_review_candidates:
                logger.info(f"Trying network JSON extraction with {len(network_review_candidates)} candidates...")

                for safe_text, rating in network_review_candidates.values():
                    if len(reviews_data) >= max_reviews:
                        break

                    review_obj = create_review_record(
                        len(reviews_data) + 1,
                        safe_text,
                        rating
                    )

                    is_valid, validation_msg = validate_review(review_obj)
                    if not is_valid:
                        skipped_count += 1
                        logger.debug(f"Skipped network review: {validation_msg}")
                        continue

                    content_hash = compute_content_hash(safe_text)
                    if content_hash in reviews_hash_set:
                        continue

                    reviews_data.append(review_obj)
                    reviews_hash_set.add(content_hash)
                    extracted_count += 1
            
            for index, element in enumerate(all_review_elements):
                if len(reviews_data) >= max_reviews:
                    logger.info(f"✓ Reached max_reviews limit ({max_reviews})")
                    break
                
                try:
                    safe_text = await extract_review_text_from_element(element)
                    rating = await extract_rating_from_element(element)
                    review_obj = create_review_record(
                        len(reviews_data) + 1,
                        safe_text,
                        rating
                    )
                    
                    # Validate review
                    is_valid, validation_msg = validate_review(review_obj)
                    
                    if is_valid:
                        # Check untuk duplicate berdasarkan content hash
                        content_hash = compute_content_hash(safe_text)
                        if content_hash not in reviews_hash_set:
                            reviews_data.append(review_obj)
                            reviews_hash_set.add(content_hash)
                            extracted_count += 1
                            
                            if extracted_count % 10 == 0:
                                logger.info(f"📥 Extracted {extracted_count} reviews...")
                    else:
                        skipped_count += 1
                        logger.debug(f"Skipped review {index + 1}: {validation_msg}")
                        
                except Exception as e:
                    logger.debug(f"Error extracting review {index + 1}: {str(e)[:60]}")
                    continue
            
            logger.info(f"Selector extraction result: {extracted_count} valid, {skipped_count} skipped")
            if not reviews_data:
                await asyncio.sleep(1)

            if not reviews_data:
                logger.info("No reviews found with selectors. Trying visible-text fallback...")
                fallback_texts = await extract_review_text_candidates_from_page(page, max_reviews)
                logger.info(f"Visible-text fallback found {len(fallback_texts)} candidates")

                for safe_text in fallback_texts:
                    if len(reviews_data) >= max_reviews:
                        break

                    review_obj = create_review_record(
                        len(reviews_data) + 1,
                        safe_text,
                        0
                    )

                    is_valid, validation_msg = validate_review(review_obj)
                    if not is_valid:
                        skipped_count += 1
                        logger.debug(f"Skipped fallback review: {validation_msg}")
                        continue

                    content_hash = compute_content_hash(safe_text)
                    if content_hash in reviews_hash_set:
                        continue

                    reviews_data.append(review_obj)
                    reviews_hash_set.add(content_hash)
                    extracted_count += 1

            if not reviews_data:
                logger.warning(
                    "No valid reviews extracted. Halaman kemungkinan masih skeleton/loading atau respons review diblokir. "
                    "Saving debug snapshot: debug_no_reviews_found.*"
                )
                await save_debug_snapshot(page, "no_reviews_found")

            logger.info(f"Final extraction result: {extracted_count} valid, {skipped_count} skipped")

        except Exception as e:
            logger.error(f"❌ Scraper error: {e}")
            import traceback
            traceback.print_exc()
            
            # Retry logic untuk network errors
            if retry_count < config.MAX_RETRIES:
                logger.info(f"🔄 Retrying due to error... ({retry_count + 1}/{config.MAX_RETRIES})")
                return await scrape_reviews_advanced(url, max_reviews, use_cache, retry_count + 1, headless)
            raise
        
        finally:
            if browser:
                await browser.close()
            
    reviews_data = enrich_reviews_with_nlp(reviews_data)

    # Save ke cache sebelum return
    if reviews_data and use_cache:
        save_to_cache(url, reviews_data)
    
    return reviews_data

# ==========================================
# 5. EXPORT DATA WITH STATISTICS
# ==========================================
def save_to_csv(data: list, filename: str) -> bool:
    """Simpan data ke CSV dengan format yang rapi dan sorted."""
    if not data:
        logger.warning("❌ No data to save")
        return False
    
    try:
        data = enrich_reviews_with_nlp(data)
        if pd is not None:
            df = pd.DataFrame(data)
            df = df.sort_values('date_scraped', ascending=False)
            df.to_csv(filename, index=False, encoding='utf-8')
            row_count = len(df)
        else:
            sorted_data = sorted(data, key=lambda row: str(row.get('date_scraped', '')), reverse=True)
            fieldnames = []
            for row in sorted_data:
                for key in row.keys():
                    if key not in fieldnames:
                        fieldnames.append(key)

            with open(filename, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sorted_data)
            row_count = len(sorted_data)

        logger.info(f"✓ CSV saved: {filename} ({row_count} rows)")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving CSV: {e}")
        return False

def save_to_json(data: list, filename: str) -> bool:
    """Simpan data ke JSON untuk dashboard dengan validation."""
    if not data:
        logger.warning("❌ No data to save")
        return False
    
    try:
        data = enrich_reviews_with_nlp(data)
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"✓ JSON saved: {filename} ({len(data)} records)")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving JSON: {e}")
        return False

def print_statistics(data: List[Dict]):
    """Print detailed statistics tentang scraped data."""
    if not data:
        logger.warning("No data to analyze")
        return

    if pd is not None:
        df = pd.DataFrame(data)
        
        logger.info("\n" + "=" * 70)
        logger.info("📊 SCRAPING STATISTICS")
        logger.info("=" * 70)
        logger.info(f"Total Reviews Extracted: {len(df)}")
        logger.info(f"Date Range: {df['date_scraped'].min()} to {df['date_scraped'].max()}")
        
        if 'rating' in df.columns:
            logger.info(f"\n⭐ Rating Distribution:")
            logger.info(f"  Average: {df['rating'].mean():.2f}/5")
            logger.info(f"  Median: {df['rating'].median():.1f}/5")
            logger.info(f"  Std Dev: {df['rating'].std():.2f}")
            logger.info(f"  Min: {df['rating'].min()} | Max: {df['rating'].max()}")
            
            rating_dist = df['rating'].value_counts().sort_index(ascending=False)
            for rating, count in rating_dist.items():
                percentage = (count / len(df)) * 100
                logger.info(f"    {int(rating)} stars: {count:3d} ({percentage:5.1f}%)")
        
        if 'sentiment' in df.columns:
            logger.info(f"\n💭 Sentiment Distribution:")
            sentiment_dist = df['sentiment'].value_counts()
            for sentiment, count in sentiment_dist.items():
                percentage = (count / len(df)) * 100
                logger.info(f"    {sentiment.capitalize():10s}: {count:3d} ({percentage:5.1f}%)")
        
        if 'text_length' in df.columns:
            logger.info(f"\n📝 Text Length Statistics:")
            logger.info(f"  Average: {df['text_length'].mean():.0f} characters")
            logger.info(f"  Median: {df['text_length'].median():.0f} characters")
            logger.info(f"  Min: {df['text_length'].min()} | Max: {df['text_length'].max()}")
        
        logger.info("=" * 70)
        return

    ratings = []
    sentiments = Counter()
    text_lengths = []
    dates = []
    for row in data:
        try:
            rating = int(float(row.get('rating', 0)))
            if 0 <= rating <= 5:
                ratings.append(rating)
        except Exception:
            pass

        sentiment = str(row.get('sentiment', 'neutral') or 'neutral').lower()
        sentiments[sentiment] += 1

        try:
            text_lengths.append(int(float(row.get('text_length', len(str(row.get('review_text', '')))))))
        except Exception:
            text_lengths.append(len(str(row.get('review_text', ''))))

        if row.get('date_scraped'):
            dates.append(str(row.get('date_scraped')))
    
    logger.info("\n" + "=" * 70)
    logger.info("📊 SCRAPING STATISTICS")
    logger.info("=" * 70)
    logger.info(f"Total Reviews Extracted: {len(data)}")
    if dates:
        logger.info(f"Date Range: {min(dates)} to {max(dates)}")
    
    if ratings:
        logger.info(f"\n⭐ Rating Distribution:")
        sorted_ratings = sorted(ratings)
        median = sorted_ratings[len(sorted_ratings) // 2]
        logger.info(f"  Average: {sum(ratings) / len(ratings):.2f}/5")
        logger.info(f"  Median: {median:.1f}/5")
        logger.info(f"  Min: {min(ratings)} | Max: {max(ratings)}")
        
        rating_dist = Counter(ratings)
        for rating in sorted(rating_dist.keys(), reverse=True):
            count = rating_dist[rating]
            percentage = (count / len(data)) * 100
            logger.info(f"    {int(rating)} stars: {count:3d} ({percentage:5.1f}%)")
    
    if sentiments:
        logger.info(f"\n💭 Sentiment Distribution:")
        for sentiment, count in sentiments.most_common():
            percentage = (count / len(data)) * 100
            logger.info(f"    {sentiment.capitalize():10s}: {count:3d} ({percentage:5.1f}%)")
    
    if text_lengths:
        sorted_lengths = sorted(text_lengths)
        median_length = sorted_lengths[len(sorted_lengths) // 2]
        logger.info(f"\n📝 Text Length Statistics:")
        logger.info(f"  Average: {sum(text_lengths) / len(text_lengths):.0f} characters")
        logger.info(f"  Median: {median_length:.0f} characters")
        logger.info(f"  Min: {min(text_lengths)} | Max: {max(text_lengths)}")
    
    logger.info("=" * 70)

# ==========================================
# 6. CONCURRENT SCRAPING FOR MULTIPLE URLs
# ==========================================
async def scrape_multiple_urls(
    urls: List[str],
    max_reviews_per_url: int = 100,
    use_cache: bool = True,
    headless: Optional[bool] = None
) -> Dict[str, List[Dict]]:
    """Scrape multiple URLs secara concurrent dengan rate limiting."""
    results = {}
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_TASKS)
    
    async def scrape_with_semaphore(url):
        async with semaphore:
            logger.info(f"\n🔗 Processing URL: {url[:50]}...")
            try:
                data = await scrape_reviews_advanced(
                    url,
                    max_reviews_per_url,
                    use_cache=use_cache,
                    headless=headless
                )
                results[url] = data
                logger.info(f"✓ Completed: {len(data)} reviews")
            except Exception as e:
                logger.error(f"❌ Failed: {e}")
                results[url] = []
    
    logger.info(f"🚀 Starting concurrent scraping for {len(urls)} URLs...")
    await asyncio.gather(*[scrape_with_semaphore(url) for url in urls])
    
    return results

# ==========================================
# 7. MAIN EXECUTION
# ==========================================
def parse_args(args: Optional[List[str]] = None):
    """Parse CLI arguments untuk menjalankan scraper tanpa hard-coded URL."""
    parser = argparse.ArgumentParser(description="Scrape ulasan produk Tokopedia.")
    parser.add_argument("--url", action="append", help="URL produk. Bisa dipakai berulang untuk multi-URL.")
    parser.add_argument("--url-file", help="File teks berisi satu URL produk per baris.")
    parser.add_argument("--max-reviews", type=int, default=100, help="Jumlah maksimum ulasan per URL.")
    parser.add_argument("--output-csv", default="dataset_ulasan_tokopedia.csv", help="Path output CSV.")
    parser.add_argument("--output-json", default="dataset_ulasan_tokopedia.json", help="Path output JSON.")
    parser.add_argument("--no-cache", action="store_true", help="Paksa scrape baru tanpa cache.")
    parser.add_argument("--headless", action="store_true", help="Jalankan Chromium tanpa UI.")
    return parser.parse_args(args)

def load_urls_from_args(args) -> List[str]:
    urls = list(args.url or [])
    if args.url_file:
        try:
            with open(args.url_file, "r", encoding="utf-8") as f:
                urls.extend(line.strip() for line in f if line.strip() and not line.strip().startswith("#"))
        except Exception as e:
            logger.error(f"Failed reading URL file: {e}")

    return urls or [DEFAULT_TARGET_URL]

def flatten_results(results: Dict[str, List[Dict]]) -> List[Dict]:
    merged = []
    for url, reviews in results.items():
        for review in reviews:
            item = dict(review)
            item["source_url"] = url
            item["id"] = len(merged) + 1
            merged.append(item)
    return merged

async def main(cli_args: Optional[List[str]] = None):
    """Main scraper execution dengan error handling."""
    args = parse_args(cli_args)
    urls = load_urls_from_args(args)
    use_cache = not args.no_cache
    
    # Print banner
    banner = """
    ╔════════════════════════════════════════════════════════════╗
    ║   TOKOPEDIA ADVANCED REVIEW SCRAPER v3.0                  ║
    ║                                                            ║
    ║   ✨ Features:                                            ║
    ║   • Smart Caching & Retry Logic                          ║
    ║   • Intelligent Lazy-Load Detection                      ║
    ║   • Enhanced Error Recovery                              ║
    ║   • Data Validation & Deduplication                      ║
    ║   • Rate Limiting & Concurrent Support                  ║
    ║   • Structured Logging & Statistics                      ║
    ║                                                            ║
    ╚════════════════════════════════════════════════════════════╝
    """
    logger.info(banner)
    
    try:
        logger.info("🌐 Starting single URL scrape...")
        if len(urls) == 1:
            extracted_data = await scrape_reviews_advanced(
                url=urls[0],
                max_reviews=args.max_reviews,
                use_cache=use_cache,
                headless=args.headless
            )
        else:
            results = await scrape_multiple_urls(
                urls,
                max_reviews_per_url=args.max_reviews,
                use_cache=use_cache,
                headless=args.headless
            )
            extracted_data = flatten_results(results)
        
        if extracted_data:
            # Save data
            save_to_csv(extracted_data, args.output_csv)
            save_to_json(extracted_data, args.output_json)
            
            # Print statistics
            print_statistics(extracted_data)
            
            logger.info("✓ Processing complete!")
        else:
            logger.warning("⚠️ No reviews extracted")
            
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
