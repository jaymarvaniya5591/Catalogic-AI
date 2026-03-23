import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

from config import UPLOAD_DIR


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
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        for i, img_url in enumerate(image_urls[:10]):
            try:
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
            except Exception:
                continue
    return saved


def _to_hires_amazon(url: str) -> str:
    """Transform Amazon thumbnail URL to high-res version."""
    return re.sub(r"\._[A-Z]{2}\d+_?\.", "._SL1500_.", url)


async def _scrape_amazon(page, url: str, session_id: str) -> dict:
    """Extract product data from Amazon page."""
    await page.goto(url, timeout=15000, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Title
    title = ""
    try:
        el = await page.query_selector("#productTitle")
        if el:
            title = (await el.inner_text()).strip()
    except Exception:
        pass

    # Images — try data-a-dynamic-image first (most reliable)
    image_urls = []
    try:
        landing = await page.query_selector("#landingImage")
        if landing:
            dyn = await landing.get_attribute("data-a-dynamic-image")
            if dyn:
                parsed = json.loads(dyn)
                image_urls = list(parsed.keys())
    except Exception:
        pass

    # Fallback: thumbnail strip
    if not image_urls:
        try:
            thumbs = await page.query_selector_all("#altImages .a-button-thumbnail img")
            for thumb in thumbs:
                src = await thumb.get_attribute("src")
                if src and "icon" not in src.lower():
                    image_urls.append(_to_hires_amazon(src))
        except Exception:
            pass

    # Fallback: main image src
    if not image_urls:
        try:
            landing = await page.query_selector("#landingImage")
            if landing:
                src = (await landing.get_attribute("data-old-hires")) or (await landing.get_attribute("src"))
                if src:
                    image_urls.append(src)
        except Exception:
            pass

    # De-duplicate while preserving order
    seen = set()
    unique_urls = []
    for u in image_urls:
        normalized = re.sub(r"\._[A-Z]{2}\d+_?\.", "", u)
        if normalized not in seen:
            seen.add(normalized)
            unique_urls.append(u)
    image_urls = unique_urls

    # Features
    features = []
    try:
        items = await page.query_selector_all("#feature-bullets .a-list-item")
        for item in items:
            text = (await item.inner_text()).strip()
            if text and len(text) > 2:
                features.append(text)
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

    # Download images
    images = await _download_images(image_urls, session_id)

    return {
        "success": True,
        "platform": "amazon",
        "title": title,
        "description": description,
        "features": features,
        "images": images,
        "error": None,
    }


async def _scrape_flipkart(page, url: str, session_id: str) -> dict:
    """Extract product data from Flipkart page."""
    await page.goto(url, timeout=15000, wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Title — try multiple selectors (Flipkart changes class names)
    title = ""
    for selector in ["span.VU-ZEz", "h1.yhB1nd", "span.B_NuCI", "h1._9E25nV"]:
        try:
            el = await page.query_selector(selector)
            if el:
                title = (await el.inner_text()).strip()
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
                    # Transform thumbnail to high-res
                    src = re.sub(r"/\d+/\d+/", "/832/832/", src)
                    image_urls.append(src)
            if image_urls:
                break
        except Exception:
            continue

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
                break
        except Exception:
            continue

    # Description
    description = ""
    for selector in ["div._4gvKMe", "div.yN\\+eNk", "div._1mXcCf"]:
        try:
            el = await page.query_selector(selector)
            if el:
                description = (await el.inner_text()).strip()[:2000]
                break
        except Exception:
            continue

    # Download images
    images = await _download_images(image_urls, session_id)

    return {
        "success": True,
        "platform": "flipkart",
        "title": title,
        "description": description,
        "features": features,
        "images": images,
        "error": None,
    }


async def scrape_product_url(url: str, session_id: str) -> dict:
    """
    Main scraper entry point. Detects platform, scrapes product data, downloads images.

    Returns dict with: success, platform, title, description, features, images[], error
    """
    platform = _detect_platform(url)
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

    browser = None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
        )
        # Evade bot detection
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        if platform == "amazon":
            return await _scrape_amazon(page, url, session_id)
        else:
            return await _scrape_flipkart(page, url, session_id)

    except asyncio.TimeoutError:
        return {
            "success": False,
            "platform": platform,
            "title": "",
            "description": "",
            "features": [],
            "images": [],
            "error": "Page took too long to load. Try uploading images manually.",
        }
    except Exception as e:
        return {
            "success": False,
            "platform": platform,
            "title": "",
            "description": "",
            "features": [],
            "images": [],
            "error": f"Could not scrape this page: {str(e)}",
        }
    finally:
        if browser:
            await browser.close()
