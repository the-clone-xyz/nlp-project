#!/usr/bin/env python3
"""
TOKOPEDIA REVIEWS SCRAPER & ANALYTICS PLATFORM
================================================
Complete solution for scraping and analyzing Tokopedia product reviews
with advanced features:
- Infinite scroll detection and handling
- Sentiment analysis using TextBlob
- Comprehensive GUI dashboard
- Advanced data visualization
- Report generation

Author: Advanced Scraper System
Date: 2026
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def can_launch_headed_browser() -> bool:
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True

def print_banner():
    """Print application banner."""
    banner = """
    ╔════════════════════════════════════════════════════════════╗
    ║   TOKOPEDIA REVIEWS SCRAPER & ANALYTICS PLATFORM v3.0      ║
    ║                                                            ║
    ║   🔍 Advanced Web Scraping with Playwright               ║
    ║   📊 Sentiment Analysis & Data Visualization             ║
    ║   📈 Interactive Dashboard & Report Generation           ║
    ╚════════════════════════════════════════════════════════════╝
    """
    print(banner)

def check_dependencies():
    """Check if all required packages are installed."""
    required_packages = {
        'pandas': 'pandas',
        'playwright': 'playwright',
        'playwright_stealth': 'playwright-stealth',
        'textblob': 'textblob',
        'matplotlib': 'matplotlib',
        'tkinter': 'tkinter'
    }
    
    missing = []
    for module, package in required_packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    
    if missing:
        print("\n⚠️  MISSING DEPENDENCIES")
        print("=" * 50)
        print("The following packages are required but not installed:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nInstall them using:")
        print(f"  pip install {' '.join(missing)}")
        print("=" * 50)
        return False
    
    return True

def install_dependencies():
    """Install required dependencies."""
    print("\n📦 Installing dependencies...")
    print("=" * 50)
    
    # Install via pip
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q',
                   'pandas', 'playwright', 'playwright_stealth', 
                   'textblob', 'matplotlib'], check=False)
    
    # Download Playwright browsers
    print("📥 Downloading Playwright browsers...")
    subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], 
                  check=False)
    
    print("✅ Dependencies installed successfully!")
    print("=" * 50)

def prompt_scraper_options():
    """Ask user for scraper options from the interactive menu."""
    print("\nMasukkan URL produk Tokopedia yang ingin di-scrape.")
    print("Contoh: https://www.tokopedia.com/nama-toko/nama-produk")
    url = input("URL produk: ").strip()

    if not url:
        print("\nScraping dibatalkan: URL tidak boleh kosong.")
        return None

    if not url.startswith(("http://", "https://")):
        print("\nURL tidak valid. URL harus diawali http:// atau https://")
        return None

    if "tokopedia.com" not in url.lower():
        print("\nPeringatan: URL bukan domain tokopedia.com.")
        confirm = input("Tetap lanjut? (y/n): ").strip().lower()
        if confirm != "y":
            print("\nScraping dibatalkan.")
            return None

    max_reviews_raw = input("Jumlah maksimal ulasan [100]: ").strip()
    if max_reviews_raw:
        try:
            max_reviews = int(max_reviews_raw)
            if max_reviews <= 0:
                raise ValueError
        except ValueError:
            print("\nJumlah ulasan tidak valid. Menggunakan default 100.")
            max_reviews = 100
    else:
        max_reviews = 100

    cache_raw = input("Gunakan cache jika tersedia? (y/n) [n]: ").strip().lower()
    use_cache = cache_raw == "y"

    default_headless = not can_launch_headed_browser()
    default_label = "y" if default_headless else "n"
    headless_raw = input(f"Jalankan browser tanpa tampilan/headless? (y/n) [{default_label}]: ").strip().lower()
    headless = default_headless if not headless_raw else headless_raw == "y"
    if not headless and not can_launch_headed_browser():
        print("\nBrowser visual tidak tersedia karena XServer/DISPLAY tidak ada. Menggunakan mode headless.")
        headless = True

    return {
        "url": url,
        "max_reviews": max_reviews,
        "use_cache": use_cache,
        "headless": headless,
    }

def run_scraper():
    """Run the advanced scraper."""
    print("\n🔍 STARTING ADVANCED SCRAPER")
    print("=" * 50)
    print("\nThis will scrape reviews from Tokopedia with:")
    print("  ✓ Infinite scroll detection")
    print("  ✓ Smart selector fallback")
    print("  ✓ Sentiment analysis")
    print("  ✓ Rating extraction")
    print("  ✓ Data deduplication")
    print("\n")
    
    options = prompt_scraper_options()
    if options is None:
        return False

    try:
        import scraper_ecomm_advanced
        extracted_data = asyncio.run(
            scraper_ecomm_advanced.scrape_reviews_advanced(
                url=options["url"],
                max_reviews=options["max_reviews"],
                use_cache=options["use_cache"],
                headless=options["headless"],
            )
        )

        if not extracted_data:
            print("\nTidak ada ulasan valid yang berhasil diekstrak.")
            print("CSV lama tidak ditimpa. Jika browser masih menampilkan skeleton/loading, cek file debug_no_reviews_found.png/html/txt.")
            print("Jalankan ulang dengan cache = n dan biarkan browser terbuka sampai card ulasan benar-benar muncul.")
            return False

        scraper_ecomm_advanced.save_to_csv(extracted_data, "dataset_ulasan_tokopedia.csv")
        scraper_ecomm_advanced.save_to_json(extracted_data, "dataset_ulasan_tokopedia.json")
        scraper_ecomm_advanced.print_statistics(extracted_data)
    except Exception as e:
        print(f"\n❌ Error running scraper: {e}")
        return False
    
    return True

def run_dashboard():
    """Run the interactive dashboard."""
    print("\n📊 LAUNCHING DASHBOARD")
    print("=" * 50)
    
    # Check if data exists
    if not os.path.exists("dataset_ulasan_tokopedia.csv"):
        print("\n⚠️  No data found!")
        print("Please run the scraper first to generate data.")
        return False
    
    print("\nLaunching interactive dashboard...")
    print("Features:")
    print("  ✓ Overview with multiple charts")
    print("  ✓ Sentiment analysis visualization")
    print("  ✓ Rating distribution")
    print("  ✓ Text analysis")
    print("  ✓ Interactive data table")
    print("  ✓ HTML report export")
    print("\n")
    
    try:
        import dashboard
        dashboard.main()
    except Exception as e:
        print(f"\n❌ Error launching dashboard: {e}")
        return False
    
    return True

def show_menu():
    """Display main menu."""
    print("\n" + "=" * 50)
    print("MAIN MENU")
    print("=" * 50)
    print("1. 🔍 Run Advanced Scraper (input URL produk)")
    print("2. 📊 Launch Dashboard (visualize data)")
    print("3. 📋 View Data Statistics")
    print("4. 🔄 Check Dependencies")
    print("5. ⚙️  Install Missing Dependencies")
    print("6. 🧹 Clean Up Cache Files")
    print("7. 📖 View Help")
    print("8. ❌ Exit")
    print("=" * 50)

def view_statistics():
    """Display data statistics."""
    try:
        import pandas as pd

        if not os.path.exists("dataset_ulasan_tokopedia.csv"):
            print("\nNo data found. Run scraper first.")
            return

        df = pd.read_csv("dataset_ulasan_tokopedia.csv")
        try:
            from scraper_ecomm_advanced import enrich_reviews_with_nlp
            df = pd.DataFrame(enrich_reviews_with_nlp(df.to_dict('records')))
        except Exception:
            pass

        print("\nDATA STATISTICS")
        print("=" * 50)
        print(f"Total Reviews:          {len(df)}")
        print(f"Average Rating:         {df['rating'].mean():.2f}/5.0")
        print(f"Average Text Length:    {df['text_length'].mean():.0f} characters")
        print("\nSentiment Distribution:")
        for sentiment, count in df['sentiment'].value_counts().items():
            percentage = (count / len(df)) * 100
            print(f"  {sentiment.upper():12} {count:4d} reviews ({percentage:5.1f}%)")

        print("\nRating Breakdown:")
        for rating in sorted(df['rating'].unique()):
            count = len(df[df['rating'] == rating])
            percentage = (count / len(df)) * 100
            print(f"  {int(rating)} stars: {count:4d} reviews ({percentage:5.1f}%)")

        if {'nlp_tokens', 'nlp_no_stopwords', 'nlp_stems', 'vector_terms'}.issubset(df.columns):
            def _count_sequence_items(series):
                total = 0
                for value in series:
                    if isinstance(value, list):
                        total += len(value)
                    elif isinstance(value, str):
                        total += len([item for item in value.strip("[]").split(",") if item.strip()])
                return total

            vector_terms = df.iloc[0]['vector_terms'] if len(df) else []
            if isinstance(vector_terms, list):
                vector_count = len(vector_terms)
            else:
                vector_count = len([item for item in str(vector_terms).strip("[]").split(",") if item.strip()])

            print("\nNLP Pipeline:")
            print(f"  Tokenization:        {_count_sequence_items(df['nlp_tokens'])} tokens")
            print(f"  Stopword Removal:    {_count_sequence_items(df['nlp_no_stopwords'])} tokens")
            print(f"  Stemming:            {_count_sequence_items(df['nlp_stems'])} stems")
            print(f"  Vectorization:       {vector_count} corpus features")

        print("=" * 50)
        return

    except Exception as e:
        print(f"\nError: {e}")
        return

    try:
        import pandas as pd
        
        if not os.path.exists("dataset_ulasan_tokopedia.csv"):
            print("\n⚠️  No data found! Run scraper first.")
            return
        
        df = pd.read_csv("dataset_ulasan_tokopedia.csv")
        try:
            from scraper_ecomm_advanced import enrich_reviews_with_nlp
            df = pd.DataFrame(enrich_reviews_with_nlp(df.to_dict('records')))
        except Exception:
            pass
        
        print("\n📈 DATA STATISTICS")
        print("=" * 50)
        print(f"Total Reviews:          {len(df)}")
        print(f"Average Rating:         {df['rating'].mean():.2f}/5.0 ⭐")
        print(f"Average Text Length:    {df['text_length'].mean():.0f} characters")
        print(f"\nSentiment Distribution:")
        for sentiment, count in df['sentiment'].value_counts().items():
            percentage = (count / len(df)) * 100
            print(f"  {sentiment.upper():12} {count:4d} reviews ({percentage:5.1f}%)")
        print(f"\nRating Breakdown:")
        for rating in sorted(df['rating'].unique()):
            count = len(df[df['rating'] == rating])
            percentage = (count / len(df)) * 100
            print(f"  ⭐ {int(rating)} stars: {count:4d} reviews ({percentage:5.1f}%)")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

def cleanup_cache():
    """Clean up cache and debug files."""
    cache_files = [
        "debug_error.png",
        "debug_error_advanced.png",
        "debug_found_reviews.png",
        "debug_page_structure.png",
        "debug_no_reviews.png",
        "debug_page.html",
        "__pycache__"
    ]
    
    print("\n🧹 CLEANING UP CACHE")
    print("=" * 50)
    
    for file in cache_files:
        if os.path.exists(file):
            try:
                if os.path.isdir(file):
                    import shutil
                    shutil.rmtree(file)
                else:
                    os.remove(file)
                print(f"  ✓ Removed {file}")
            except Exception as e:
                print(f"  ✗ Failed to remove {file}: {e}")
    
    print("=" * 50)

def show_help():
    """Display help information."""
    help_text = """
    📖 HELP & DOCUMENTATION
    ================================================================
    
    🔍 ADVANCED SCRAPER
    ────────────────────
    Features:
    - Infinite scroll detection and automatic scrolling
    - Multiple CSS selector fallbacks
    - Smart deduplication using text matching
    - Sentiment analysis for Indonesian review text
    - Rating extraction from review elements
    - JSON and CSV export formats
    
    Usage:
    1. Run the scraper from main menu (option 1)
    2. Enter the Tokopedia product URL when prompted
    3. Choose max reviews, cache, and headless options
    4. Wait for Chromium browser to open and scrape reviews
    5. Data saved to dataset_ulasan_tokopedia.csv
    
    📊 INTERACTIVE DASHBOARD
    ────────────────────────
    Features:
    - 6 different analysis tabs
    - Real-time statistics display
    - Multiple chart types (pie, bar, histogram, scatter)
    - Interactive data table with sorting
    - HTML report generation
    - CSV file loading support
    
    Tabs:
    1. Overview     - Summary stats and 4-chart overview
    2. Sentiment    - Sentiment distribution analysis
    3. Rating       - Star rating breakdown
    4. Text         - Review text length analysis
    5. Reviews Data - Full data table with filters
    
    💡 TIPS
    ──────
    - Run scraper during off-peak hours for better results
    - Close the browser window after scraping completes
    - Dashboard loads data automatically from CSV
    - Export reports as HTML for sharing
    - Multiple runs append new data (check for duplicates)
    
    ⚠️  COMMON ISSUES
    ────────────────
    Q: Scraper times out
    A: Tokopedia may be blocking or slow. Retry or increase timeout.
    
    Q: No reviews found
    A: Product may have no reviews or structure changed.
    
    Q: Dashboard won't open
    A: Ensure tkinter is installed and data exists.
    
    📞 SUPPORT
    ──────────
    For issues, check:
    - requirements_final.txt for dependencies
    - debug PNG files for error screenshots
    - Console output for detailed error messages
    
    ================================================================
    """
    print(help_text)

def main():
    """Main application loop."""
    print_banner()
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required!")
        sys.exit(1)
    
    # Check dependencies on first run
    first_run = True
    
    while True:
        show_menu()
        choice = input("\nSelect option (1-8): ").strip()
        
        if choice == "1":
            if first_run and not check_dependencies():
                print("\nWould you like to install dependencies? (y/n): ", end="")
                if input().lower() == 'y':
                    install_dependencies()
                    first_run = False
                else:
                    continue
            
            if run_scraper():
                print("\n✅ Scraper completed successfully!")
        
        elif choice == "2":
            if run_dashboard():
                pass  # Dashboard runs in blocking mode
        
        elif choice == "3":
            view_statistics()
        
        elif choice == "4":
            if check_dependencies():
                print("\n✅ All dependencies installed!")
            else:
                print("\n❌ Some dependencies are missing.")
        
        elif choice == "5":
            install_dependencies()
            first_run = False
        
        elif choice == "6":
            cleanup_cache()
        
        elif choice == "7":
            show_help()
        
        elif choice == "8":
            print("\n👋 Thank you for using Tokopedia Reviews Scraper!")
            print("=" * 50)
            sys.exit(0)
        
        else:
            print("\n❌ Invalid option. Please select 1-8.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Application interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
