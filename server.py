import os
import uuid
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from zipfile import ZipFile

from config import UPLOAD_DIR, OUTPUT_DIR
from scraper import scrape_product_url
from gemini_service import (
    analyze_competitor_catalog,
    analyze_user_product_images,
    generate_master_context_block,
    generate_hero_image,
    generate_catalog_image,
)

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
        "costs": [],
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


# ── Analysis/Q&A Helpers ──

COMPETITOR_IMAGE_CAP = 12

# Attribute family mapping: related attribute IDs grouped so that knowing
# any member suppresses questions about the entire family.
ATTRIBUTE_FAMILIES: dict[str, list[str]] = {
    "dimensions": [
        "dimensions", "total_height", "total_depth", "bowl_height",
        "product_dimensions", "max_outer_width", "base_width",
        "bowl_depth", "seat_height", "overall_length", "overall_width",
        "overall_height", "rough_in_distance", "height", "width", "depth",
        "inlet_hole_diameter", "hole_spacing", "bowl_outer_rim",
        "internal_bowl_width", "rim_length",
    ],
    "material_finish": [
        "material_finish", "material", "finish", "glazing_type",
        "surface_finish", "body_material",
    ],
    "flush_system_type": [
        "flush_system_type", "flush_method", "flush_type", "flushing_system",
    ],
    "trap_outlet_type": [
        "trap_outlet_type", "s_trap_or_p_trap", "trap_type", "outlet_type",
    ],
    "product_color": [
        "product_color", "color", "finish_color", "colour",
    ],
    "rough_in_inches": [
        "rough_in_inches", "rough_in_distance", "roughin",
    ],
}

# Reverse lookup: attribute_id → family name
_ATTR_TO_FAMILY: dict[str, str] = {}
for _family, _members in ATTRIBUTE_FAMILIES.items():
    for _member in _members:
        _ATTR_TO_FAMILY[_member] = _family


def _normalize_text(s: str) -> str:
    return (s or "").strip().lower()


def extract_user_value_map(product_description: str) -> dict[str, str]:
    """
    Lightweight extraction of user-provided attributes from free text.
    If we can't confidently extract, we return nothing and let defaults handle it.
    """
    desc = _normalize_text(product_description)
    values: dict[str, str] = {}

    # Flush system / method
    if "siphonic" in desc:
        values["flush_system_type"] = "siphonic flush"
    elif "jet" in desc:
        values["flush_system_type"] = "jet flush"
    elif "washdown" in desc:
        values["flush_system_type"] = "washdown"

    # Trap / outlet type
    if "s-trap" in desc or "s trap" in desc:
        values["trap_outlet_type"] = "S trap"
        values["s_trap_or_p_trap"] = "S trap"
    elif "p-trap" in desc or "p trap" in desc:
        values["trap_outlet_type"] = "P trap"
        values["s_trap_or_p_trap"] = "P trap"

    # Rough-in inches (e.g., "9 inch rough-in")
    if "rough" in desc and "inch" in desc:
        import re

        m = re.search(r"(\\d{1,2})\\s*(?:inch|in)\\b", desc)
        if m:
            values["rough_in_inches"] = f"{m.group(1)} inch"

    # Material / finish
    for token in ["ceramic", "porcelain", "vitreous", "stainless", "chrome", "polished"]:
        if token in desc:
            values["material_finish"] = token
            break

    # Rim type
    if "rimless" in desc:
        values["rim_type"] = "rimless"
    elif "rim" in desc:
        values["rim_type"] = "rimmed"

    # Bumper design
    if "bumper" in desc:
        values["bumper_design"] = "bumper"

    # Dimensions presence (we only use this for skip heuristics)
    if any(w in desc for w in ["dimension", "dimensions", "mm", "inch", "cm", "length", "width", "height", "size"]):
        values["dimensions"] = "dimensions provided"

    return values


# Keywords in user-image OCR text that indicate a family is already provided
_FAMILY_OCR_KEYWORDS: dict[str, list[str]] = {
    "dimensions": ["mm", "inch", "height", "width", "depth", "cm", "dimension", "dimensions"],
    "material_finish": ["ceramic", "porcelain", "vitreous", "stainless", "chrome"],
    "flush_system_type": ["siphonic", "washdown", "jet flush"],
    "trap_outlet_type": ["s-trap", "p-trap", "s trap", "p trap"],
    "rough_in_inches": ["rough-in", "rough in", "roughin"],
    # product_color: intentionally empty — "white"/"black" too generic for OCR matching
}


def _enrich_user_values_from_image_analysis(
    user_values: dict[str, str],
    user_image_analysis: dict,
) -> None:
    """
    Enrich user_values in-place from Gemini's analysis of the user's own product images.
    - Merges extracted attributes (lower confidence threshold since these are the user's images)
    - Scans OCR detected_text for family keywords to mark entire families as provided
    - Registers family-level keys so should_skip_question_for_claim catches family matches
    """
    # 1. Merge extracted attributes with lowered confidence threshold
    for attr in (user_image_analysis.get("extracted_attributes") or []):
        attr_id = (attr.get("attribute_id") or "").strip()
        attr_val = (attr.get("value") or "").strip()
        confidence = float(attr.get("confidence", 0) or 0)
        if attr_id and attr_val and confidence >= 0.25:
            if attr_id not in user_values:
                user_values[attr_id] = attr_val
            # Also register the family so family-level skip works
            family = _ATTR_TO_FAMILY.get(attr_id)
            if family and family not in user_values:
                user_values[family] = attr_val

    # 2. Scan OCR detected_text for family keywords
    all_detected_text: list[str] = []
    for summary in (user_image_analysis.get("image_summaries") or []):
        all_detected_text.extend(summary.get("detected_text") or [])

    ocr_blob = " ".join(all_detected_text).lower()

    for family, keywords in _FAMILY_OCR_KEYWORDS.items():
        if family not in user_values:
            if any(kw in ocr_blob for kw in keywords):
                user_values[family] = "detected in user image"


def build_attribute_defaults_from_analysis(analysis: dict) -> dict[str, dict]:
    """
    Build attribute defaults from Gemini-extracted claims across all competitor images
    and across any suggested additions' required claims.
    """
    best: dict[str, dict] = {}

    def consider_claim(claim: dict):
        attr = (claim.get("attribute_id") or "").strip()
        if not attr:
            return
        conf = float(claim.get("confidence", 0) or 0)
        value = (claim.get("value") or "").strip()
        if not value:
            return
        if attr not in best or conf > float(best[attr].get("confidence", 0) or 0):
            best[attr] = {
                "value": value,
                "confidence": conf,
                "label": (claim.get("label") or attr).strip(),
            }

    for img in (analysis.get("images", []) or []):
        for claim in (img.get("claims", []) or []):
            consider_claim(claim)

    for add in (analysis.get("suggested_additions", []) or []):
        for claim in (add.get("required_claims", []) or []):
            consider_claim(claim)

    return best


def should_skip_question_for_claim(
    attribute_id: str,
    claim_value: str,
    product_description: str,
    user_values: dict[str, str],
) -> bool:
    """
    Skip asking if we can reasonably infer the user already provided this attribute.
    Checks direct match, attribute-family match, and text-description match.
    """
    desc = _normalize_text(product_description)

    # Direct match
    if attribute_id in user_values:
        return True

    # Family match: if the attribute belongs to a family and any member
    # (or the family key itself) is already in user_values, skip it.
    family = _ATTR_TO_FAMILY.get(attribute_id)
    if family:
        if family in user_values:
            return True
        for member in ATTRIBUTE_FAMILIES.get(family, []):
            if member in user_values:
                return True

    # Claim value found verbatim in text description
    if claim_value and _normalize_text(claim_value) in desc:
        return True

    # Rough-in skip heuristic
    if "rough_in" in attribute_id and "rough" in desc and "inch" in desc:
        return True

    return False


def _evidence_from_snippets(snippets: list[str], prefer_keywords: list[str] | None = None) -> str:
    if not snippets:
        return ""
    snippets = [s for s in snippets if s]
    if not snippets:
        return ""
    text = " ".join(snippets).lower()
    if prefer_keywords:
        for kw in prefer_keywords:
            k = kw.lower()
            idx = text.find(k)
            if idx != -1:
                # Return snippet that contains keyword if possible
                for s in snippets:
                    if k in s.lower():
                        return s[:200].strip()
    return snippets[0][:200].strip()


def extract_attribute_claims_from_visible_text(
    visible_text_snippets: list[str],
) -> list[dict]:
    """
    Convert OCR-visible text snippets into structured competitor claims.
    This is deliberately conservative: it only creates claims for common sanitaryware specs.
    """
    t = " ".join(visible_text_snippets or []).lower()
    claims: list[dict] = []

    def add_claim(attribute_id: str, label: str, value: str, answer_type: str = "text", options=None, evidence_keywords=None, confidence: float = 0.85):
        if not attribute_id or not value:
            return
        evidence_text = _evidence_from_snippets(visible_text_snippets or [], prefer_keywords=evidence_keywords)
        claims.append({
            "attribute_id": attribute_id,
            "label": label,
            "value": value,
            "answer_type": answer_type,
            "options": options,
            "confidence": confidence,
            "evidence_text": evidence_text,
        })

    # Flush system type
    if "siphonic" in t:
        add_claim(
            "flush_system_type",
            "Flush system type",
            "siphonic flush",
            answer_type="choice",
            options=["siphonic flush", "jet flush", "washdown flush"],
            evidence_keywords=["siphonic"],
        )
    elif "washdown" in t:
        add_claim(
            "flush_system_type",
            "Flush system type",
            "washdown flush",
            answer_type="choice",
            options=["siphonic flush", "jet flush", "washdown flush"],
            evidence_keywords=["washdown"],
        )
    elif "jet flush" in t or ("jet" in t and "flush" in t):
        add_claim(
            "flush_system_type",
            "Flush system type",
            "jet flush",
            answer_type="choice",
            options=["siphonic flush", "jet flush", "washdown flush"],
            evidence_keywords=["jet"],
        )

    # Trap / outlet type
    if "s-trap" in t or "s trap" in t:
        add_claim(
            "s_trap_or_p_trap",
            "Trap outlet type",
            "S trap",
            answer_type="choice",
            options=["S trap", "P trap"],
            evidence_keywords=["s-trap", "s trap"],
        )
    elif "p-trap" in t or "p trap" in t:
        add_claim(
            "s_trap_or_p_trap",
            "Trap outlet type",
            "P trap",
            answer_type="choice",
            options=["S trap", "P trap"],
            evidence_keywords=["p-trap", "p trap"],
        )

    # Rough-in inches / outlet connection distance (often described as X inches from the wall)
    if "inch" in t and ("rough" in t or "from the wall" in t or "outlet" in t):
        import re

        # Examples: "9 inches from wall" / "9 inch rough-in"
        m = re.search(r"([0-9]{1,2}(?:\\.[0-9])?)\\s*(?:inches|inch|in)\\b", t)
        if m:
            add_claim(
                "rough_in_inches",
                "Rough-in distance",
                f"{m.group(1)} inch",
                answer_type="text",
                options=None,
                evidence_keywords=["rough", "inch"],
                confidence=0.8,
            )

    # Bumper design
    if "bumper" in t:
        add_claim(
            "bumper_design",
            "Bumper design",
            "bumper",
            answer_type="choice",
            options=["bumper", "no bumper / standard mechanism"],
            evidence_keywords=["bumper"],
        )

    # Rim type
    if "rimless" in t:
        add_claim(
            "rim_type",
            "Rim type",
            "rimless",
            answer_type="choice",
            options=["rimless", "rimmed"],
            evidence_keywords=["rimless"],
        )
    elif "rim" in t:
        add_claim(
            "rim_type",
            "Rim type",
            "rimmed",
            answer_type="choice",
            options=["rimless", "rimmed"],
            evidence_keywords=["rim"],
            confidence=0.6,
        )

    # Soft close seat / slow close
    if "soft close" in t or "soft-closing" in t or "soft closing" in t:
        add_claim(
            "seat_close_type",
            "Seat closing type",
            "soft close",
            answer_type="choice",
            options=["soft close", "standard close"],
            evidence_keywords=["soft close", "soft closing"],
        )

    # Material / finish
    if "ceramic" in t:
        add_claim(
            "material_finish",
            "Material / finish",
            "ceramic",
            answer_type="choice",
            options=["ceramic", "porcelain", "stainless/chrome (metal)"],
            evidence_keywords=["ceramic"],
            confidence=0.75,
        )

    return claims


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

    try:
        result = await scrape_product_url(url, session_id)
    except Exception as e:
        print(f"[SERVER] Scrape crashed: {type(e).__name__}: {e}")
        return {
            "success": False,
            "session_id": session_id,
            "platform": "unknown",
            "title": "",
            "description": "",
            "features": [],
            "images": [],
            "error": f"Scraper error: {type(e).__name__}: {e}",
        }

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
    images: list[UploadFile] = File(default=[]),
    description: str = Form(""),
    session_id: str = Form(...),
):
    """Upload user's own product images + description."""
    if session_id not in sessions:
        return {"success": False, "error": "Invalid session"}

    # Filter out empty file slots (browser may send an empty part)
    real_images = [f for f in (images or []) if f and getattr(f, "filename", None)]
    image_paths = await save_upload_files(real_images, session_id, "product") if real_images else []

    session = sessions[session_id]
    session["product"]["description"] = description
    session["product"]["images"] = image_paths

    return {
        "success": True,
        "session_id": session_id,
        "images": image_paths,
        "description": description,
    }


@app.post("/api/analyze")
async def analyze(payload: dict):
    """Run competitor analysis pipeline: analyze → extract claims → build targeted questions."""
    session_id = payload.get("session_id", "")
    if session_id not in sessions:
        return {"success": False, "error": "Invalid session"}

    session = sessions[session_id]
    competitor = session["competitor"]
    product = session["product"]

    if not competitor["images"]:
        return {"success": False, "error": "No competitor images found"}

    try:
        # Step 1: Analyze competitor catalog images + user product images IN PARALLEL
        description = competitor.get("description", "")
        features = competitor.get("features", [])
        full_description = description + "\n" + "\n".join(features)

        # Cost control: cap competitor images sent to Gemini
        competitor_images = competitor.get("images", [])[:COMPETITOR_IMAGE_CAP]
        session["competitor"]["images"] = competitor_images

        product_images = product.get("images", [])
        product_description = product.get("description", "")

        # Run both analyses in parallel
        competitor_task = analyze_competitor_catalog(competitor_images, full_description)
        user_task = analyze_user_product_images(product_images[:5], product_description)

        (analysis, cost1), (user_image_analysis, cost2) = await asyncio.gather(
            competitor_task, user_task
        )

        # Step 2: Merge user-known attributes from description (rule-based)
        #         + Gemini user image analysis (attributes + OCR text + family grouping)
        user_values = extract_user_value_map(product_description)
        _enrich_user_values_from_image_analysis(user_values, user_image_analysis)

        # Step 3: Build attribute defaults from competitor analysis
        attribute_defaults = build_attribute_defaults_from_analysis(analysis)

        compiled_attributes: dict[str, str] = {
            k: v.get("value", "") for k, v in attribute_defaults.items()
        }
        for attr_id, val in user_values.items():
            compiled_attributes[attr_id] = val

        # Step 4: Build questions from Gemini claims (with skip + dedup)
        questions: list[dict] = []
        question_ids: set[str] = set()

        for img in analysis.get("images", []) or []:
            img_index = int(img.get("index", 0))
            for claim in img.get("claims", []) or []:
                attribute_id = (claim.get("attribute_id") or "").strip()
                if not attribute_id:
                    continue

                if should_skip_question_for_claim(
                    attribute_id=attribute_id,
                    claim_value=claim.get("value") or "",
                    product_description=product_description,
                    user_values=user_values,
                ):
                    continue

                answer_type = claim.get("answer_type") or "text"
                question_type = "text"
                options = None
                if answer_type == "choice":
                    question_type = "choice"
                    options = claim.get("options") or None
                elif answer_type == "image":
                    question_type = "image"

                label = (claim.get("label") or attribute_id).strip()
                value = (claim.get("value") or "").strip()
                confidence = float(claim.get("confidence", 0) or 0)
                evidence_text = (claim.get("evidence_text") or "").strip()

                questions.append({
                    "id": f"{attribute_id}_img{img_index}",
                    "attribute_id": attribute_id,
                    "group": {"kind": "competitor_image", "image_index": img_index},
                    "text": f"From the competitor image, it looks like `{label}` is `{value}`. Is this true for your product?",
                    "type": question_type,
                    "options": options,
                    "default_value": value,
                    "context": evidence_text,
                    "confidence": confidence,
                    "source_value": value,
                })
                question_ids.add(f"{attribute_id}_img{img_index}")

            # If Gemini claims are incomplete/missing, fall back to heuristics on visible OCR snippets.
            visible_text_snippets = img.get("visible_text_snippets", []) or []
            heuristic_claims = extract_attribute_claims_from_visible_text(visible_text_snippets)
            for claim in heuristic_claims:
                attribute_id = (claim.get("attribute_id") or "").strip()
                if not attribute_id:
                    continue

                qid = f"{attribute_id}_img{img_index}"
                if qid in question_ids:
                    continue

                if should_skip_question_for_claim(
                    attribute_id=attribute_id,
                    claim_value=claim.get("value") or "",
                    product_description=product_description,
                    user_values=user_values,
                ):
                    continue

                answer_type = claim.get("answer_type") or "text"
                question_type = "text"
                options = None
                if answer_type == "choice":
                    question_type = "choice"
                    options = claim.get("options") or None
                elif answer_type == "image":
                    question_type = "image"

                label = (claim.get("label") or attribute_id).strip()
                value = (claim.get("value") or "").strip()
                evidence_text = (claim.get("evidence_text") or "").strip()
                confidence = float(claim.get("confidence", 0) or 0)

                questions.append({
                    "id": qid,
                    "attribute_id": attribute_id,
                    "group": {"kind": "competitor_image", "image_index": img_index},
                    "text": f"From the competitor image, it appears `{label}` is `{value}`. Is this true for your product?",
                    "type": question_type,
                    "options": options,
                    "default_value": value,
                    "context": evidence_text,
                    "confidence": confidence,
                    "source_value": value,
                })
                question_ids.add(qid)

        # Suggested additions: ask for their required claims too
        for add in analysis.get("suggested_additions", []) or []:
            addition_id = (add.get("id") or "").strip()
            if not addition_id:
                continue
            for claim in add.get("required_claims", []) or []:
                attribute_id = (claim.get("attribute_id") or "").strip()
                if not attribute_id:
                    continue

                if should_skip_question_for_claim(
                    attribute_id=attribute_id,
                    claim_value=claim.get("value") or "",
                    product_description=product_description,
                    user_values=user_values,
                ):
                    continue

                answer_type = claim.get("answer_type") or "text"
                question_type = "text"
                options = None
                if answer_type == "choice":
                    question_type = "choice"
                    options = claim.get("options") or None
                elif answer_type == "image":
                    question_type = "image"

                label = (claim.get("label") or attribute_id).strip()
                value = (claim.get("value") or "").strip()
                confidence = float(claim.get("confidence", 0) or 0)
                evidence_text = (claim.get("evidence_text") or "").strip()

                questions.append({
                    "id": f"{addition_id}_{attribute_id}",
                    "attribute_id": attribute_id,
                    "group": {"kind": "suggested_addition", "addition_id": addition_id},
                    "text": f"For the suggested catalog addition, it appears your product should have `{label}` = `{value}`. Confirm?",
                    "type": question_type,
                    "options": options,
                    "default_value": value,
                    "context": evidence_text,
                    "confidence": confidence,
                    "source_value": value,
                })

        # Step 5: Deduplicate questions by attribute_id (keep first occurrence = earliest image)
        seen_attrs: set[str] = set()
        deduped_questions: list[dict] = []
        for q in questions:
            attr_id = q.get("attribute_id", "")
            group_kind = q.get("group", {}).get("kind", "")
            # Dedup key: attribute_id for competitor questions, full id for additions
            dedup_key = attr_id if group_kind == "competitor_image" else q.get("id", attr_id)
            if dedup_key in seen_attrs:
                continue
            seen_attrs.add(dedup_key)
            deduped_questions.append(q)
        questions = deduped_questions

        # Step 6: Build image_display_data for frontend accordion
        image_display_data = []
        for img in analysis.get("images", []) or []:
            idx = int(img.get("index", 0))
            img_questions = [
                q for q in questions
                if q.get("group", {}).get("kind") == "competitor_image"
                and q.get("group", {}).get("image_index") == idx
            ]
            image_display_data.append({
                "index": idx,
                "image_url": competitor_images[idx] if idx < len(competitor_images) else None,
                "type": img.get("type", "other"),
                "summary": img.get("summary") or img.get("intent", ""),
                "question_count": len(img_questions),
                "questions": img_questions,
            })

        # Store in session
        session["analysis"] = analysis
        session["questions"] = questions
        session["compiled_attributes"] = compiled_attributes
        session["user_image_analysis"] = user_image_analysis
        session["selected_additions"] = []
        costs_list = [cost1]
        if cost2 and cost2.get("input_tokens", 0) > 0:
            costs_list.append(cost2)
        session["costs"].extend(costs_list)

        total_cost_inr = sum(c.get("cost_inr", 0) for c in session["costs"])

        return {
            "success": True,
            "analysis": analysis,
            "questions": questions,
            "image_display_data": image_display_data,
            "costs": costs_list,
            "total_cost_inr": round(total_cost_inr, 4),
        }
    except Exception as e:
        print(f"[SERVER] Analysis failed: {type(e).__name__}: {e}")
        return {"success": False, "error": f"Analysis failed: {str(e)}"}


@app.post("/api/answers")
async def submit_answers(
    session_id: str = Form(...),
    answers_json: str = Form("{}"),
    selected_additions_json: str = Form("[]"),
    image_qids_json: str = Form("[]"),
    image_files: list[UploadFile] = File([]),
):
    """Save user's answers to smart questions (multipart), merging defaults for skipped ones."""
    if session_id not in sessions:
        return {"success": False, "error": "Invalid session"}

    session = sessions[session_id]

    try:
        answers = json.loads(answers_json) if answers_json else {}
    except Exception:
        answers = {}

    try:
        selected_addition_ids = json.loads(selected_additions_json) if selected_additions_json else []
    except Exception:
        selected_addition_ids = []

    try:
        image_qids = json.loads(image_qids_json) if image_qids_json else []
    except Exception:
        image_qids = []

    # Merge defaults for skipped/empty answers
    if session["questions"]:
        for q in session["questions"]:
            if q["id"] not in answers or not answers[q["id"]]:
                answers[q["id"]] = q.get("default_value", "")

    # Save uploaded answer images and map them to qids.
    # Frontend sends files in the same order as `image_qids_json`.
    saved_image_urls: dict[str, str] = {}
    for i, file in enumerate(image_files or []):
        qid = str(image_qids[i]) if i < len(image_qids) else f"image_qid_{i}"
        ext = Path(file.filename).suffix or ".jpg"
        dir_path = Path(UPLOAD_DIR) / session_id / "answers"
        dir_path.mkdir(parents=True, exist_ok=True)
        filename = f"{qid}{ext}"
        file_path = dir_path / filename

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        saved_image_urls[qid] = f"/uploads/{session_id}/answers/{filename}"

    # If an answer image was uploaded for a question, store the URL in answers.
    for qid, url in saved_image_urls.items():
        answers[qid] = url

    session["answers"] = answers
    session["selected_additions"] = selected_addition_ids

    # Update compiled_attributes using answers where relevant.
    if "compiled_attributes" not in session:
        session["compiled_attributes"] = {}
    for q in (session.get("questions") or []):
        qid = q.get("id")
        attr_id = q.get("attribute_id")
        if qid and attr_id and qid in answers and answers.get(qid):
            session["compiled_attributes"][attr_id] = answers[qid]

    return {"success": True, "answers": answers, "selected_additions": selected_addition_ids}


# ── Phase 4/5: Hero + Catalog Generation ──

@app.post("/api/generate-hero")
async def api_generate_hero(
    session_id: str = Form(...),
    regenerate: bool = Form(False),
    hero_override: UploadFile = File(None),
):
    if session_id not in sessions:
        return {"success": False, "error": "Invalid session"}

    session = sessions[session_id]

    try:
        # If user uploaded a hero image, accept it directly (no Gemini call).
        if hero_override is not None and getattr(hero_override, "filename", None):
            hero_dir = Path(OUTPUT_DIR) / session_id / "hero"
            hero_dir.mkdir(parents=True, exist_ok=True)
            out_path = hero_dir / "hero.png"

            content = await hero_override.read()
            with open(out_path, "wb") as f:
                f.write(content)

            hero_url = f"/outputs/{session_id}/hero/hero.png"
            session["hero_image"] = hero_url
            return {"success": True, "hero_image_url": hero_url, "mode": "user_override", "costs": []}

        product = session.get("product") or {}
        product_description = product.get("description", "")
        product_images = product.get("images", []) or []
        compiled_attributes = session.get("compiled_attributes", {}) or {}

        timeout_s = 120  # increased to account for master context generation
        if not regenerate and session.get("hero_image"):
            return {"success": True, "hero_image_url": session["hero_image"], "mode": "cached", "costs": []}

        # Generate master context block (rich product description + photography style)
        # This replaces dry key-value attributes with natural-language prose
        if not session.get("master_context_block") or regenerate:
            try:
                master_context, mc_cost = await asyncio.wait_for(
                    generate_master_context_block(
                        product_images,
                        product_description,
                        compiled_attributes,
                    ),
                    timeout=30,
                )
                session["master_context_block"] = master_context
                session["costs"].append(mc_cost)
            except Exception as e:
                print(f"[WARN] Master context generation failed, using fallback: {e}")
                session["master_context_block"] = ""

        hero_url, cost = await asyncio.wait_for(
            generate_hero_image(
                session_id,
                product_images,
                product_description,
                compiled_attributes,
                master_context=session.get("master_context_block", ""),
            ),
            timeout=timeout_s,
        )

        session["hero_image"] = hero_url
        session["costs"].append(cost)
        total_cost_inr = sum(c.get("cost_inr", 0) for c in session["costs"])
        return {"success": True, "hero_image_url": hero_url, "mode": "generated", "costs": [cost], "total_cost_inr": total_cost_inr}
    except asyncio.TimeoutError:
        return {"success": False, "error": "HERO_TIMEOUT", "message": "Hero generation timed out. Please retry or upload your own hero image."}
    except Exception as e:
        return {"success": False, "error": f"HERO_FAILED:{type(e).__name__}", "message": str(e)}


@app.get("/api/generate-catalog/stream")
async def api_generate_catalog_stream(session_id: str):
    if session_id not in sessions:
        return {"success": False, "error": "Invalid session"}

    session = sessions[session_id]
    analysis = session.get("analysis") or {}
    competitor_images = session.get("competitor", {}).get("images", []) or []
    hero_image_url = session.get("hero_image")
    compiled_attributes = session.get("compiled_attributes", {}) or {}
    selected_addition_ids = session.get("selected_additions", []) or []

    if not hero_image_url:
        async def gen_err():
            yield "event: error\ndata: " + json.dumps({"error": "HERO_NOT_GENERATED"}) + "\n\n"

        return StreamingResponse(gen_err(), media_type="text/event-stream")

    analysis_images = analysis.get("images", []) or []
    by_index = {int(img.get("index", 0)): img for img in analysis_images}
    recommended_order = analysis.get("recommended_order") or [img.get("index", 0) for img in analysis_images]

    jobs: list[dict] = []
    for idx in recommended_order:
        if int(idx) not in by_index:
            continue
        img = by_index[int(idx)]
        competitor_url = competitor_images[int(idx)] if int(idx) < len(competitor_images) else None
        jobs.append({
            "key": f"competitor_{int(idx)}",
            "type": "competitor",
            "image_type": img.get("type") or "other",
            "reference_intent_image_url": competitor_url,
            "style_prompt": img.get("style_prompt") or "",
            "prompt_fragment": f"INTENT: {img.get('intent') or ''}\nVISUAL ELEMENTS: {', '.join([str(x) for x in (img.get('key_elements') or [])])}\nDETAILED SCENE DESCRIPTION: {img.get('summary') or ''}",
            "image_key": f"competitor_{int(idx)}",
            "image_index": int(idx),
        })

    additions = analysis.get("suggested_additions", []) or []
    additions_by_id = {a.get("id"): a for a in additions if a.get("id")}
    for aid in selected_addition_ids:
        add = additions_by_id.get(aid)
        if not add:
            continue
        jobs.append({
            "key": f"addition_{aid}",
            "type": "addition",
            "reference_intent_image_url": None,
            "style_prompt": "Consistent studio product photography styling (match the HERO look).",
            "prompt_fragment": add.get("generation_prompt_fragment") or add.get("title") or aid,
            "image_key": f"addition_{aid}",
            "addition_id": aid,
        })

    # For prompt_fragment we may have non-string types; normalize
    for job in jobs:
        frag = job.get("prompt_fragment")
        if isinstance(frag, list):
            job["prompt_fragment"] = " ".join([str(x) for x in frag if x])

    total = len(jobs)

    async def sse_generator():
        sem = asyncio.Semaphore(2)  # cost/rate limiting
        queue: asyncio.Queue = asyncio.Queue()
        completed = 0
        questions = session.get("questions") or []
        answers = session.get("answers") or {}

        # Emit start event
        yield "event: catalog_start\ndata: " + json.dumps({"total": total}) + "\n\n"

        async def run_job(job: dict):
            nonlocal completed
            async with sem:
                try:
                    timeout_s = 180
                    job_compiled_attributes = dict(compiled_attributes or {})
                    if job.get("type") == "competitor":
                        job_idx = job.get("image_index")
                        for q in questions:
                            if (
                                q.get("group", {}).get("kind") == "competitor_image"
                                and q.get("group", {}).get("image_index") == job_idx
                            ):
                                qid = q.get("id")
                                attr_id = q.get("attribute_id")
                                if qid and attr_id and answers.get(qid):
                                    job_compiled_attributes[attr_id] = answers[qid]
                    elif job.get("type") == "addition":
                        job_aid = job.get("addition_id")
                        for q in questions:
                            if (
                                q.get("group", {}).get("kind") == "suggested_addition"
                                and q.get("group", {}).get("addition_id") == job_aid
                            ):
                                qid = q.get("id")
                                attr_id = q.get("attribute_id")
                                if qid and attr_id and answers.get(qid):
                                    job_compiled_attributes[attr_id] = answers[qid]

                    # Compute changed attributes (diff from competitor defaults)
                    changed_attrs = {}
                    if job.get("type") == "competitor":
                        job_idx = job.get("image_index")
                        img_data = by_index.get(job_idx, {})
                        competitor_claims = {
                            (c.get("attribute_id") or "").strip(): (c.get("value") or "").strip()
                            for c in (img_data.get("claims") or [])
                        }
                        for attr_id, val in job_compiled_attributes.items():
                            comp_val = competitor_claims.get(attr_id, "")
                            if comp_val and str(val).strip().lower() != comp_val.lower():
                                changed_attrs[attr_id] = val

                    image_url, cost = await asyncio.wait_for(
                        generate_catalog_image(
                            session_id,
                            job["image_key"],
                            hero_image_url,
                            job.get("reference_intent_image_url"),
                            job.get("style_prompt") or "",
                            job.get("prompt_fragment") or "",
                            job_compiled_attributes,
                            changed_attributes=changed_attrs or None,
                            master_context=session.get("master_context_block", ""),
                            image_type=job.get("image_type") or "other",
                        ),
                        timeout=timeout_s,
                    )
                    queue.put_nowait({
                        "status": "success",
                        "key": job["key"],
                        "image_url": image_url,
                        "cost": cost,
                    })
                except asyncio.TimeoutError:
                    queue.put_nowait({
                        "status": "timeout",
                        "key": job["key"],
                        "image_url": None,
                    })
                except Exception as e:
                    queue.put_nowait({
                        "status": "failed",
                        "key": job["key"],
                        "image_url": None,
                        "error": str(e),
                    })

        tasks = [asyncio.create_task(run_job(job)) for job in jobs]

        while completed < total:
            event = await queue.get()
            completed += 1

            # Update session state as we go (for download/regenerate later)
            if event.get("status") == "success":
                session.setdefault("catalog_images", []).append({
                    "key": event["key"],
                    "url": event["image_url"],
                })
                session["costs"].append(event.get("cost") or {})

            yield "event: catalog_image\ndata: " + json.dumps(event) + "\n\n"

        # Ensure background tasks end
        for t in tasks:
            if not t.done():
                t.cancel()

        yield "event: catalog_done\ndata: " + json.dumps({"total": total}) + "\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@app.post("/api/regenerate")
async def api_regenerate_catalog(
    session_id: str = Form(...),
    image_key: str = Form(...),
    feedback: str = Form(""),
):
    if session_id not in sessions:
        return {"success": False, "error": "Invalid session"}

    session = sessions[session_id]
    analysis = session.get("analysis") or {}
    competitor_images = session.get("competitor", {}).get("images", []) or []
    hero_image_url = session.get("hero_image")
    compiled_attributes = session.get("compiled_attributes", {}) or {}

    if not hero_image_url:
        return {"success": False, "error": "HERO_NOT_GENERATED"}

    analysis_images = analysis.get("images", []) or []
    by_index = {int(img.get("index", 0)): img for img in analysis_images}

    reference_intent_image_url = None
    style_prompt = ""
    prompt_fragment = ""

    regen_image_type = "other"

    if image_key.startswith("competitor_"):
        idx = int(image_key.replace("competitor_", ""))
        img = by_index.get(idx)
        if not img:
            return {"success": False, "error": "IMAGE_NOT_FOUND"}
        reference_intent_image_url = competitor_images[idx] if idx < len(competitor_images) else None
        style_prompt = img.get("style_prompt") or ""
        prompt_fragment = f"INTENT: {img.get('intent') or ''}\nVISUAL ELEMENTS: {', '.join([str(x) for x in (img.get('key_elements') or [])])}\nDETAILED SCENE DESCRIPTION: {img.get('summary') or ''}"
        regen_image_type = img.get("type") or "other"
    elif image_key.startswith("addition_"):
        aid = image_key.replace("addition_", "")
        additions = analysis.get("suggested_additions", []) or []
        add = next((a for a in additions if a.get("id") == aid), None)
        if not add:
            return {"success": False, "error": "IMAGE_NOT_FOUND"}
        reference_intent_image_url = None
        style_prompt = "Consistent studio product photography styling (match the HERO look)."
        prompt_fragment = add.get("generation_prompt_fragment") or ""
    else:
        return {"success": False, "error": "INVALID_IMAGE_KEY"}

    # Append any regeneration feedback (if provided by future UI)
    if feedback and isinstance(feedback, str):
        prompt_fragment = (prompt_fragment or "") + f"\nUser feedback: {feedback}"

    try:
        image_url, cost = await asyncio.wait_for(
            generate_catalog_image(
                session_id,
                image_key,
                hero_image_url,
                reference_intent_image_url,
                style_prompt,
                prompt_fragment,
                compiled_attributes,
                master_context=session.get("master_context_block", ""),
                image_type=regen_image_type,
            ),
            timeout=180,
        )
        session.setdefault("catalog_images", []).append({"key": image_key, "url": image_url})
        session["costs"].append(cost)
        return {"success": True, "image_url": image_url}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/download/{session_id}")
async def api_download_catalog(session_id: str):
    if session_id not in sessions:
        return {"success": False, "error": "Invalid session"}

    catalog_dir = Path(OUTPUT_DIR) / session_id / "catalog"
    if not catalog_dir.exists():
        return {"success": False, "error": "No generated catalog found"}

    zip_path = Path(OUTPUT_DIR) / session_id / "catalog.zip"
    if zip_path.exists():
        zip_path.unlink()

    with ZipFile(zip_path, "w") as zf:
        for p in catalog_dir.rglob("*"):
            if p.is_file():
                arc = p.relative_to(Path(OUTPUT_DIR) / session_id)
                zf.write(p, arcname=str(arc))

    return FileResponse(zip_path, media_type="application/zip", filename="catalog.zip")


# Mount static directories (after all route definitions)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
