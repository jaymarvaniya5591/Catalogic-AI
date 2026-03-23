import os
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import UPLOAD_DIR, OUTPUT_DIR
from scraper import scrape_product_url

BASE_DIR = Path(__file__).parent

# Create directories
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Ruva Catalog Generator")

# In-memory session storage
sessions = {}


# ── Helpers ──

def create_session(session_id: str) -> dict:
    """Create a new session with default structure."""
    session = {
        "id": session_id,
        "competitor": {
            "mode": None,
            "url": None,
            "platform": None,
            "title": "",
            "description": "",
            "features": [],
            "images": [],
        },
        "product": {
            "description": "",
            "images": [],
        },
        "analysis": None,
        "questions": None,
        "answers": None,
        "hero_image": None,
        "catalog_images": [],
    }
    sessions[session_id] = session
    return session


async def save_upload_files(
    files: list[UploadFile], session_id: str, subfolder: str
) -> list[str]:
    """Save uploaded files to uploads/{session_id}/{subfolder}/. Returns URL paths."""
    dir_path = Path(UPLOAD_DIR) / session_id / subfolder
    dir_path.mkdir(parents=True, exist_ok=True)

    paths = []
    for i, file in enumerate(files):
        ext = Path(file.filename).suffix or ".jpg"
        filename = f"img_{i}{ext}"
        file_path = dir_path / filename

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        paths.append(f"/uploads/{session_id}/{subfolder}/{filename}")
    return paths


# ── Routes ──

@app.get("/")
async def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "ruva-catalog-generator"}


@app.post("/api/scrape")
async def scrape_url(payload: dict):
    """Scrape a competitor product URL and return images + metadata."""
    url = (payload.get("url") or "").strip()
    if not url:
        return {"success": False, "error": "URL is required"}

    session_id = uuid.uuid4().hex
    session = create_session(session_id)

    result = await scrape_product_url(url, session_id)

    # Update session with scraped data
    session["competitor"]["mode"] = "url"
    session["competitor"]["url"] = url
    session["competitor"]["platform"] = result.get("platform")
    session["competitor"]["title"] = result.get("title", "")
    session["competitor"]["description"] = result.get("description", "")
    session["competitor"]["features"] = result.get("features", [])
    session["competitor"]["images"] = result.get("images", [])

    return {
        "success": result["success"],
        "session_id": session_id,
        "platform": result.get("platform"),
        "title": result.get("title", ""),
        "description": result.get("description", ""),
        "features": result.get("features", []),
        "images": result.get("images", []),
        "error": result.get("error"),
    }


@app.post("/api/upload-competitor")
async def upload_competitor(
    images: list[UploadFile] = File(...),
    description: str = Form(""),
    session_id: str = Form(""),
):
    """Manual competitor image upload fallback."""
    if not session_id:
        session_id = uuid.uuid4().hex
        create_session(session_id)
    elif session_id not in sessions:
        create_session(session_id)

    image_paths = await save_upload_files(images, session_id, "competitor")

    session = sessions[session_id]
    session["competitor"]["mode"] = "upload"
    session["competitor"]["description"] = description
    session["competitor"]["images"] = image_paths

    return {
        "success": True,
        "session_id": session_id,
        "images": image_paths,
        "description": description,
    }


@app.post("/api/upload-product")
async def upload_product(
    images: list[UploadFile] = File(...),
    description: str = Form(""),
    session_id: str = Form(...),
):
    """Upload user's own product images + description."""
    if session_id not in sessions:
        return {"success": False, "error": "Invalid session"}

    image_paths = await save_upload_files(images, session_id, "product")

    session = sessions[session_id]
    session["product"]["description"] = description
    session["product"]["images"] = image_paths

    return {
        "success": True,
        "session_id": session_id,
        "images": image_paths,
        "description": description,
    }


# Mount static directories (after all route definitions)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
