import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

from config import UPLOAD_DIR


def _log(msg: str):
    """Unicode-safe print for Windows terminals."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def _detect_platform(url: str) -> str:
    """Detect e-commerce platform from URL."""
    domain = urlparse(url).netloc.lower()
    if any(x in domain for x in ["amazon.in", "amazon.com", "amzn."]):
        return "amazon"
    if any(x in domain for x in ["flipkart.com", "fkrt.it"]):
        return "flipkart"
    return "unknown"


async def _download_images(image_urls: list[str], session_id: str) -> list[str]:
    """Download images to uploads/{session_id}/competitor/. Returns list of URL paths."""
    dir_path = Path(UPLOAD_DIR) / session_id / "competitor"
    dir_path.mkdir(parents=True, exist_ok=True)

    saved = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for i, img_url in enumerate(image_urls[:10]):
            try:
                _log(f"  Downloading image {i+1}/{len(image_urls[:10])}: {img_url[:80]}...")
                resp = await client.get(img_url)
                if resp.status_code == 200:
                    ext = ".jpg"
                    ct = resp.headers.get("content-type", "")
                    if "png" in ct:
                        ext = ".png"
                    elif "webp" in ct:
                        ext = ".webp"

                    filename = f"img_{i}{ext}"
                    with open(dir_path / filename, "wb") as f:
                        f.write(resp.content)
                    saved.append(f"/uploads/{session_id}/competitor/{filename}")
                    _log(f"  Saved {filename} ({len(resp.content)} bytes)")
                else:
                    _log(f"  Failed to download (status {resp.status_code})")
            except Exception as e:
                _log(f"  Failed to download: {e}")
                continue
    return saved


def _to_hires_amazon(url: str) -> str:
    """Transform Amazon thumbnail URL to high-res version."""
    return re.sub(r"\._[A-Z]{2}\d+_?\.", "._SL1500_.", url)


async def _scrape_amazon(page, url: str, session_id: str) -> dict:
    """Extract product data from Amazon page."""
    _log(f"[Amazon] Navigating to: {url[:80]}...")
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")

    # Wait for key elements to load (Amazon populates via JS after DOM ready)
    try:
        await page.wait_for_selector("#productTitle", timeout=8000)
        _log("[Amazon] Product title found")
    except Exception:
        _log("[Amazon] Product title not found, continuing anyway...")

    # Extra wait for images to populate via JS
    await page.wait_for_timeout(3000)

    # Title
    title = ""
    try:
        el = await page.query_selector("#productTitle")
        if el:
            title = (await el.inner_text()).strip()
            _log(f"[Amazon] Title: {title[:60]}")
    except Exception:
        pass

    # Images — Use JS to extract ALL gallery image URLs (most reliable)
    # Amazon stores high-res URLs in a JS variable called 'colorImages'
    image_urls = []
    try:
        image_urls = await page.evaluate("""
            () => {
                // Method 1: colorImages JS object (most reliable — has all gallery images)
                if (typeof colorImages !== 'undefined' && colorImages.initial) {
                    return colorImages.initial.map(img => img.hiRes || img.large).filter(Boolean);
                }
                // Method 2: ImageBlockATF data
                const scripts = document.querySelectorAll('script[type="text/javascript"]');
                for (const s of scripts) {
                    const txt = s.textContent;
                    if (txt.includes("'colorImages'")) {
                        const match = txt.match(/'colorImages':\\s*\\{\\s*'initial':\\s*(\\[.*?\\])/s);
                        if (match) {
                            try {
                                const parsed = JSON.parse(match[1].replace(/'/g, '"'));
                                return parsed.map(img => img.hiRes || img.large).filter(Boolean);
                            } catch(e) {}
                        }
                    }
                }
                return [];
            }
        """)
        if image_urls:
            _log(f"[Amazon] Found {len(image_urls)} images from colorImages JS")
    except Exception as e:
        _log(f"[Amazon] colorImages extraction failed: {e}")

    # Fallback: thumbnail strip (each thumbnail = different product image)
    if not image_urls:
        try:
            thumbs = await page.query_selector_all("#altImages .a-button-thumbnail img")
            for thumb in thumbs:
                src = await thumb.get_attribute("src")
                if src and "icon" not in src.lower() and "sprite" not in src.lower():
                    image_urls.append(_to_hires_amazon(src))
            if image_urls:
                _log(f"[Amazon] Found {len(image_urls)} images from thumbnail strip")
        except Exception as e:
            _log(f"[Amazon] Thumbnail strip failed: {e}")

    # Fallback: main landing image
    if not image_urls:
        try:
            landing = await page.query_selector("#landingImage")
            if landing:
                src = (await landing.get_attribute("data-old-hires")) or (await landing.get_attribute("src"))
                if src:
                    image_urls.append(src)
                    _log("[Amazon] Found 1 image from main image src")
        except Exception:
            pass

    if not image_urls:
        _log("[Amazon] WARNING: No images found!")

    # De-duplicate: strip size suffix to detect same base image, keep highest-res version
    seen = set()
    unique_urls = []
    for u in image_urls:
        # Extract the image ID (e.g., "81Tyl-bQ0IL" from the URL)
        base = re.sub(r"\._[A-Za-z0-9_,]+_\.", ".", u)
        if base not in seen:
            seen.add(base)
            unique_urls.append(u)
    image_urls = unique_urls
    _log(f"[Amazon] {len(image_urls)} unique images after dedup")

    # Features
    features = []
    try:
        items = await page.query_selector_all("#feature-bullets .a-list-item")
        for item in items:
            text = (await item.inner_text()).strip()
            if text and len(text) > 2:
                features.append(text)
        _log(f"[Amazon] Found {len(features)} features")
    except Exception:
        pass

    # Description
    description = ""
    try:
        el = await page.query_selector("#productDescription p")
        if el:
            description = (await el.inner_text()).strip()
    except Exception:
        pass
    if not description:
        try:
            el = await page.query_selector("#aplus_feature_div")
            if el:
                description = (await el.inner_text()).strip()[:2000]
        except Exception:
            pass
    _log(f"[Amazon] Description: {len(description)} chars")

    # Download images
    images = await _download_images(image_urls, session_id)
    _log(f"[Amazon] Downloaded {len(images)} images to disk")

    return {
        "success": len(images) > 0,
        "platform": "amazon",
        "title": title,
        "description": description,
        "features": features,
        "images": images,
        "error": None if images else "No images could be extracted from this page.",
    }


async def _scrape_flipkart(page, url: str, session_id: str) -> dict:
    """Extract product data from Flipkart page."""
    _log(f"[Flipkart] Navigating to: {url[:80]}...")
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    # Title — try multiple selectors (Flipkart changes class names)
    title = ""
    for selector in ["span.VU-ZEz", "h1.yhB1nd", "span.B_NuCI", "h1._9E25nV"]:
        try:
            el = await page.query_selector(selector)
            if el:
                title = (await el.inner_text()).strip()
                _log(f"[Flipkart] Title: {title[:60]}")
                break
        except Exception:
            continue

    # Images
    image_urls = []
    for selector in ["img._0DkuPH", "img._396cs4", "div._3kidJX img"]:
        try:
            imgs = await page.query_selector_all(selector)
            for img in imgs:
                src = await img.get_attribute("src")
                if src:
                    src = re.sub(r"/\d+/\d+/", "/832/832/", src)
                    image_urls.append(src)
            if image_urls:
                _log(f"[Flipkart] Found {len(image_urls)} images")
                break
        except Exception:
            continue

    # Fallback: try all product images via JS
    if not image_urls:
        try:
            image_urls = await page.evaluate("""
                () => {
                    const imgs = document.querySelectorAll('img[loading="eager"], div[class*="image"] img');
                    return Array.from(imgs)
                        .map(img => img.src)
                        .filter(src => src && src.includes('rukminim'));
                }
            """)
            if image_urls:
                image_urls = [re.sub(r"/\d+/\d+/", "/832/832/", u) for u in image_urls]
                _log(f"[Flipkart] Found {len(image_urls)} images via JS evaluation")
        except Exception:
            pass

    # De-duplicate
    image_urls = list(dict.fromkeys(image_urls))

    # Features
    features = []
    for selector in ["li._7eSDEz", "li.rgWa7D", "div._2418kt li"]:
        try:
            items = await page.query_selector_all(selector)
            for item in items:
                text = (await item.inner_text()).strip()
                if text and len(text) > 2:
                    features.append(text)
            if features:
                _log(f"[Flipkart] Found {len(features)} features")
                break
        except Exception:
            continue

    # Description
    description = ""
    for selector in ["div._4gvKMe", "div._1mXcCf"]:
        try:
            el = await page.query_selector(selector)
            if el:
                description = (await el.inner_text()).strip()[:2000]
                break
        except Exception:
            continue
    _log(f"[Flipkart] Description: {len(description)} chars")

    # Download images
    images = await _download_images(image_urls, session_id)
    _log(f"[Flipkart] Downloaded {len(images)} images to disk")

    return {
        "success": len(images) > 0,
        "platform": "flipkart",
        "title": title,
        "description": description,
        "features": features,
        "images": images,
        "error": None if images else "No images could be extracted from this page.",
    }


async def scrape_product_url(url: str, session_id: str) -> dict:
    """
    Main scraper entry point. On Windows, runs in a separate thread with
    ProactorEventLoop so Playwright can launch browser subprocesses
    (uvicorn's SelectorEventLoop doesn't support subprocesses).
    """
    if sys.platform == "win32":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _scrape_sync, url, session_id)
    return await _scrape_impl(url, session_id)


def _scrape_sync(url: str, session_id: str) -> dict:
    """Sync wrapper: creates a ProactorEventLoop for Playwright on Windows."""
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_scrape_impl(url, session_id))
    finally:
        loop.close()


async def _scrape_impl(url: str, session_id: str) -> dict:
    """
    Actual scraper logic. Detects platform, scrapes product data, downloads images.

    Returns dict with: success, platform, title, description, features, images[], error
    """
    platform = _detect_platform(url)
    _log(f"\n{'='*50}")
    _log(f"Scraping: {url[:80]}")
    _log(f"Platform: {platform}")
    _log(f"Session:  {session_id}")
    _log(f"{'='*50}")

    if platform == "unknown":
        return {
            "success": False,
            "platform": "unknown",
            "title": "",
            "description": "",
            "features": [],
            "images": [],
            "error": "Only Amazon and Flipkart URLs are supported.",
        }

    async with async_playwright() as pw:
        browser = None
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                java_script_enabled=True,
            )
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = await context.new_page()

            if platform == "amazon":
                result = await _scrape_amazon(page, url, session_id)
            else:
                result = await _scrape_flipkart(page, url, session_id)

            _log(f"\nScrape complete: success={result['success']}, images={len(result['images'])}")
            return result

        except Exception as e:
            if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
                _log("TIMEOUT: Page took too long to load")
                return {
                    "success": False,
                    "platform": platform,
                    "title": "",
                    "description": "",
                    "features": [],
                    "images": [],
                    "error": "Page took too long to load. Try uploading images manually.",
                }
            _log(f"ERROR: {type(e).__name__}: {e}")
            error_msg = str(e)
            if "Executable doesn't exist" in error_msg:
                error_msg = "Browser not installed. Please run .\\serve again — it will auto-install."
            return {
                "success": False,
                "platform": platform,
                "title": "",
                "description": "",
                "features": [],
                "images": [],
                "error": error_msg,
            }
        finally:
            if browser:
                await browser.close()
