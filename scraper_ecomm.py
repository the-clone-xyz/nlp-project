import asyncio
import pandas as pd
import re
import random
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ==========================================
# 1. DATA SANITIZATION (SECURITY & CLEANING)
# ==========================================
def sanitize_text(raw_text: str) -> str:
    """
    Membersihkan teks ulasan dari karakter tidak aman, newline, dan spasi berlebih.
    Mencegah rusaknya format CSV dan menetralisir potensi injeksi teks berbahaya.
    """
    if not raw_text:
        return ""
    clean_text = re.sub(r'<.*?>', '', raw_text)
    clean_text = clean_text.replace('\n', ' ').replace('\r', '')
    clean_text = re.sub(r'\s+', ' ', clean_text)
    return clean_text.strip()

# ==========================================
# 2. CORE SCRAPING LOGIC (STEALTH & LAZY LOAD)
# ==========================================
async def scrape_reviews(url: str, max_reviews: int = 50) -> list:
    reviews_data = []
    
    async with async_playwright() as p:
        # Gunakan headless=False untuk proses debugging. 
        # Jika browser tidak dibuka secara visual, Tokopedia sering langsung memblokir.
        browser = await p.chromium.launch(headless=False)
        
        # Konfigurasi fingerprint untuk menyamar sebagai browser normal
        context = await browser.new_context(
            viewport={'width': 1366, 'height': 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # [CRITICAL SECURITY BYPASS] Aktifkan stealth mode untuk menyembunyikan identitas webdriver
        stealth = Stealth()
        await stealth.apply_stealth_async(context)  # Apply ke context
        await stealth.apply_stealth_async(page)     # Apply ke page juga

        print(f"[*] Mengakses URL: {url}")
        
        try:
            # wait_until="load" lebih cepat dari networkidle, dan sudah cukup untuk content visible
            try:
                await page.goto(url, wait_until="load", timeout=60000)
            except Exception as goto_error:
                print(f"[!] Page.goto timeout/error: {goto_error}")
                print("[*] Melanjutkan dengan konten yang sudah ada...")
            
            print("[*] Halaman utama termuat. Menunggu review section dirender...")
            
            # Tunggu lebih lama untuk skeleton loading selesai
            await asyncio.sleep(5)
            
            print("[*] Memulai simulasi scroll untuk memicu lazy loading dan menyelesaikan animasi...")
            
            # Scroll dengan delay lebih panjang untuk memberi waktu animasi selesai
            for i in range(8):
                await page.mouse.wheel(0, 500)
                await asyncio.sleep(random.uniform(0.5, 1.5))
                print(f"[*] Scroll {i+1}/8")
            
            # Tunggu lagi setelah scroll
            await asyncio.sleep(3)
            
            # Coba multiple selectors karena struktur Tokopedia sering berubah
            review_selectors = [
                'span[data-testid="lblItemUlasan"]',  # Original selector
                'div[data-testid*="review"]',
                '[data-testid*="review"]',
                '.review-card',
                '.css-cat6y5',  # Common Tokopedia review class
                'div.review',
                'p[class*="review"]',
                '[class*="ReviewCard"]',
                'span[class*="review"]',
                'div[class*="feedback"]',
                'p:has-text("Pembeli")',  # Element yang berisi kata "Pembeli"
                'div[class*="sellerReview"]'
            ]
            
            review_elements = []
            for selector in review_selectors:
                print(f"[*] Mencoba selector: {selector}")
                try:
                    elements = await page.query_selector_all(selector)
                    if len(elements) > 0:
                        # Pastikan elemen tidak kosong (bukan skeleton)
                        valid_elements = []
                        for elem in elements:
                            text = await elem.inner_text()
                            if text and len(text.strip()) > 0:
                                valid_elements.append(elem)
                        
                        if len(valid_elements) > 0:
                            print(f"[✓] Berhasil dengan selector: {selector} ({len(valid_elements)} elemen valid)")
                            review_elements = valid_elements
                            break
                except Exception as e:
                    print(f"[*] Selector gagal: {selector}")
                    continue
            
            if not review_elements:
                print("[!] Tidak menemukan reviews dengan selector standar. Mengambil screenshot untuk debugging...")
                await page.screenshot(path="debug_page_structure.png")
                
                # Tampilkan HTML untuk debugging
                html_content = await page.content()
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                print("[!] Halaman HTML disimpan ke debug_page.html")
                
                # Coba ekstrak teks yang terlihat seperti review
                all_text = await page.text_content()
                print(f"[*] Ukuran halaman text: {len(all_text)} karakter")
                print(f"[*] Preview: {all_text[:200]}")
                
                # Fallback: cari semua elemen yang mungkin mengandung review
                potential_reviews = await page.query_selector_all('*')
                print(f"[*] Total elemen di halaman: {len(potential_reviews)}")
            
            print(f"[*] Berhasil mendeteksi {len(review_elements)} ulasan di halaman ini.")
            
            # Debug: ambil screenshot untuk melihat halaman saat ini
            if len(review_elements) > 0:
                await page.screenshot(path="debug_found_reviews.png")
                print("[*] Screenshot halaman tersimpan di debug_found_reviews.png")
            else:
                await page.screenshot(path="debug_no_reviews.png")
                print("[!] Screenshot (tidak ada reviews) di debug_no_reviews.png")
            
            for index, element in enumerate(review_elements):
                if index >= max_reviews:
                    break
                    
                try:
                    raw_text = await element.inner_text()
                    
                    # Jika elemen kosong, coba cari child elements yang berisi teks
                    if not raw_text or len(raw_text.strip()) == 0:
                        child_elements = await element.query_selector_all('span, p, div')
                        for child in child_elements:
                            child_text = await child.inner_text()
                            if child_text and len(child_text.strip()) > 5:
                                raw_text = child_text
                                break
                    
                    safe_text = sanitize_text(raw_text)
                    
                    # Debug: tampilkan semua teks yang ditemukan
                    if raw_text:
                        print(f"[*] Review {index + 1} raw: {raw_text[:60]}...")
                        print(f"[*] Review {index + 1} clean: {safe_text[:60]}... (len={len(safe_text)})")
                    
                    # Hanya simpan ulasan yang memiliki teks (mengabaikan ulasan yang hanya memberi bintang)
                    if safe_text and len(safe_text) > 3:
                        reviews_data.append({
                            "id": len(reviews_data) + 1,
                            "review_text": safe_text,
                            "sentiment_label": "" # Placeholder untuk model klasifikasi NLP Anda
                        })
                        print(f"[✓] Review berhasil disimpan ({len(reviews_data)}/{max_reviews})")
                    else:
                        print(f"[!] Review {index + 1} diabaikan (teks terlalu pendek atau kosong)")
                except Exception as e:
                    print(f"[!] Gagal ekstrak review {index + 1}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        except Exception as e:
            print(f"[!] Proses terhenti karena error/deteksi WAF: {e}")
            await page.screenshot(path="debug_error.png")
            print("[!] Screenshots tersimpan:")
            print("[!]  - debug_error.png (halaman error)")
            
            # Coba ambil info halaman untuk debugging
            try:
                page_title = await page.title()
                print(f"[*] Judul halaman: {page_title}")
                
                # Cek apakah ada blocking message
                blocking_messages = await page.query_selector_all('div[class*="error"], div[class*="block"], div[class*="security"]')
                if len(blocking_messages) > 0:
                    print(f"[!] Ditemukan {len(blocking_messages)} elemen yang mungkin blocking message")
            except:
                pass
        finally:
            await browser.close()
            
    return reviews_data

# ==========================================
# 3. EXPORT / DATA PIPELINE
# ==========================================
def save_to_csv(data: list, filename: str):
    if not data:
        print("[!] Tidak ada data yang berhasil diekstrak.")
        return
        
    df = pd.DataFrame(data)
    df.to_csv(filename, index=False, encoding='utf-8')
    print(f"[*] Selesai! Berhasil menyimpan {len(data)} baris data ke dalam '{filename}'")

# ==========================================
# 4. MAIN EXECUTION
# ==========================================
async def main():
    TARGET_URL = "https://www.tokopedia.com/rajaramnusantara/ssd-eyota-256gb-sata-iii-2-5-6gb-s-garansi-resmi-5-tahun-1729858241056376439?extParam=ivf%3Dfalse%26keyword%3Dssd%26search_id%3D2026042605350294F6D7E04A4D452B43CO%26src%3Dsearch&t_id=1777181726394&t_st=1&t_pp=search_result&t_efo=search_pure_goods_card&t_ef=goods_search&t_sm=&t_spt=search_result"
    
    print("=== Memulai Pipeline Ekstraksi Data NLP ===")
    
    # Batasi ke 20 ulasan terlebih dahulu untuk memvalidasi arsitektur scraper berjalan dengan baik
    extracted_data = await scrape_reviews(url=TARGET_URL, max_reviews=20)
    save_to_csv(extracted_data, "dataset_ulasan_tokopedia.csv")
    
    print("=== Eksekusi Selesai ===")

if __name__ == "__main__":
    # Menjalankan event loop asynchronous (dibutuhkan oleh Playwright)
    asyncio.run(main())