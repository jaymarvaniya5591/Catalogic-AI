"""
Gemini AI service — catalog analysis, gap detection, smart questions.
Uses the google-genai SDK (NOT the deprecated google-generativeai).
"""

import json
import time
import re
from pathlib import Path
from io import BytesIO

from PIL import Image
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, MODEL_ANALYSIS, PRICING, USD_TO_INR

# ── Lazy Client (avoids crash if key is empty at import time) ──

_client = None


def get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set. Add it to your .env file.")
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


# ── Helpers ──

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

MAX_IMAGE_BYTES = 4_000_000  # 4 MB


def _load_image_for_gemini(url_path: str) -> types.Part:
    """Convert a URL path like /uploads/abc/competitor/img_0.jpg to a Gemini Part."""
    file_path = Path(url_path.lstrip("/"))
    if not file_path.exists():
        raise FileNotFoundError(f"Image not found: {file_path}")

    image_bytes = file_path.read_bytes()
    ext = file_path.suffix.lower()
    mime_type = MIME_MAP.get(ext, "image/jpeg")

    # Resize if too large
    if len(image_bytes) > MAX_IMAGE_BYTES:
        image_bytes = _resize_image(image_bytes, mime_type)

    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)


def _resize_image(image_bytes: bytes, mime_type: str) -> bytes:
    """Downscale image to fit under MAX_IMAGE_BYTES."""
    img = Image.open(BytesIO(image_bytes))
    quality = 85
    fmt = "JPEG" if "jpeg" in mime_type or "jpg" in mime_type else "PNG"

    for scale in [0.75, 0.5, 0.35]:
        new_size = (int(img.width * scale), int(img.height * scale))
        resized = img.resize(new_size, Image.LANCZOS)
        buf = BytesIO()
        resized.save(buf, format=fmt, quality=quality)
        if buf.tell() <= MAX_IMAGE_BYTES:
            return buf.getvalue()

    # Last resort — very small
    buf = BytesIO()
    img.resize((800, 600), Image.LANCZOS).save(buf, format=fmt, quality=70)
    return buf.getvalue()


def _parse_json_response(text: str):
    """Parse JSON from Gemini response, stripping markdown fences if present."""
    cleaned = text.strip()
    # Strip ```json ... ``` wrapper
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _extract_cost(response, model_name: str) -> dict:
    """Extract token usage and calculate cost from a Gemini response."""
    cost_info = {
        "model": model_name,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
        "cost_inr": 0.0,
    }

    try:
        usage = response.usage_metadata
        if usage:
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            cost_info["input_tokens"] = input_tokens
            cost_info["output_tokens"] = output_tokens

            pricing = PRICING.get(model_name, {})
            input_cost = (input_tokens / 1_000_000) * pricing.get("input", 0)
            output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0)
            cost_info["cost_usd"] = round(input_cost + output_cost, 6)
            cost_info["cost_inr"] = round(cost_info["cost_usd"] * USD_TO_INR, 4)
    except Exception as e:
        print(f"[GEMINI] Cost extraction failed: {e}")

    return cost_info


# ── Function 1: Analyze Competitor Catalog ──

def analyze_competitor_catalog(images: list[str], description: str) -> tuple[dict, dict]:
    """
    Send all competitor images + description to Gemini.
    Returns (analysis_result, cost_info).
    """
    n = len(images)
    client = get_client()

    prompt = f"""You are a professional e-commerce catalog analyst for sanitaryware/bathroom products.

I'm showing you {n} catalog images from a competitor product listing, along with the product description.

Product description:
{description}

For each image (numbered 0 through {n - 1}), identify:
1. "type": The image category. Must be one of: "hero", "lifestyle", "closeup", "dimensions", "infographic", "comparison", "packaging", "installation", "features", "brand", "other"
2. "intent": A short description (1-2 sentences) of what this image communicates to the buyer
3. "key_elements": List of visual elements present (e.g. ["bathroom setting", "marble countertop", "warm lighting"])
4. "priority": "high", "medium", or "low" — how important this image type is for a catalog

Also provide:
- "catalog_strategy": A 2-sentence summary of the competitor's overall catalog approach
- "recommended_order": The ideal order to present images (as array of indices)

Return valid JSON with this exact structure:
{{
  "images": [
    {{"index": 0, "type": "...", "intent": "...", "key_elements": [...], "priority": "..."}},
    ...
  ],
  "catalog_strategy": "...",
  "recommended_order": [0, 2, 1, ...]
}}"""

    contents = [prompt]
    for img_path in images:
        try:
            contents.append(_load_image_for_gemini(img_path))
        except FileNotFoundError as e:
            print(f"[GEMINI] Skipping missing image: {e}")

    # Retry once on failure
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL_ANALYSIS,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            result = _parse_json_response(response.text)
            cost = _extract_cost(response, MODEL_ANALYSIS)
            cost["operation"] = "Catalog Analysis"
            return result, cost
        except Exception as e:
            print(f"[GEMINI] analyze attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                time.sleep(2)

    # Fallback: return generic structure
    fallback = {
        "images": [
            {"index": i, "type": "other", "intent": "Could not analyze", "key_elements": [], "priority": "medium"}
            for i in range(n)
        ],
        "catalog_strategy": "Analysis unavailable.",
        "recommended_order": list(range(n)),
    }
    return fallback, {"model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "cost_inr": 0, "operation": "Catalog Analysis"}


# ── Function 2: Detect Information Gaps (rule-based) ──

def detect_information_gaps(
    competitor_data: dict, product_data: dict, analysis: dict
) -> list[dict]:
    """Compare competitor catalog vs user data to find missing info. No Gemini call."""
    gaps = []
    image_types = {img.get("type") for img in analysis.get("images", [])}
    comp_desc = (competitor_data.get("description", "") + " ".join(competitor_data.get("features", []))).lower()
    user_desc = product_data.get("description", "").lower()

    # 1. Dimensions / sizes
    has_dimension_words = any(w in comp_desc for w in ["dimension", "size", "mm", "inch", "cm", "length", "width", "height"])
    user_has_dimensions = any(w in user_desc for w in ["dimension", "size", "mm", "inch", "cm", "length", "width", "height"])
    if (has_dimension_words or "dimensions" in image_types) and not user_has_dimensions:
        gaps.append({
            "id": "dimensions",
            "category": "product_specs",
            "description": "Product dimensions are shown in competitor catalog but not provided by you",
            "importance": "high",
        })

    # 2. Material / finish
    has_material = any(w in comp_desc for w in ["material", "finish", "ceramic", "stainless", "chrome", "brass", "porcelain"])
    user_has_material = any(w in user_desc for w in ["material", "finish", "ceramic", "stainless", "chrome", "brass", "porcelain"])
    if (has_material or "closeup" in image_types) and not user_has_material:
        gaps.append({
            "id": "material",
            "category": "product_specs",
            "description": "Material and finish details are featured by competitor but not specified",
            "importance": "high",
        })

    # 3. Installation / lifestyle context
    if "lifestyle" in image_types or "installation" in image_types:
        gaps.append({
            "id": "installation_context",
            "category": "usage_context",
            "description": "Competitor shows the product in a room/installation setting",
            "importance": "medium",
        })

    # 4. Brand identity
    if "brand" in image_types or "infographic" in image_types:
        gaps.append({
            "id": "brand_identity",
            "category": "brand",
            "description": "Competitor uses branded elements (logo, tagline, color scheme)",
            "importance": "medium",
        })

    # 5. Unique selling points
    if "comparison" in image_types or "features" in image_types:
        gaps.append({
            "id": "usp",
            "category": "marketing",
            "description": "Competitor highlights unique features or comparisons",
            "importance": "medium",
        })

    # 6. Photography preferences — always include
    gaps.append({
        "id": "photo_style",
        "category": "photography",
        "description": "Visual style preferences for generated images",
        "importance": "low",
    })

    return gaps


# ── Function 3: Generate Smart Questions ──

def generate_smart_questions(gaps: list[dict], analysis: dict) -> tuple[list[dict], dict]:
    """
    Turn information gaps into user-friendly questions with intelligent defaults.
    Returns (questions_list, cost_info).
    """
    if not gaps:
        return [], {"model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "cost_inr": 0, "operation": "Question Generation"}

    client = get_client()
    strategy = analysis.get("catalog_strategy", "No strategy available.")

    prompt = f"""You are helping a premium Indian sanitaryware brand called Ruva create catalog images.
Based on the information gaps identified below, generate smart questions for the user.

Gaps found:
{json.dumps(gaps, indent=2)}

Competitor catalog strategy: {strategy}

For each gap, generate a question with:
- "id": same as the gap id
- "text": A clear, friendly question (1-2 sentences max)
- "type": "text" (free text answer), "choice" (multiple choice), or "image" (user uploads an image)
- "options": If type is "choice", provide 3-5 options as a list. Otherwise null.
- "default_value": An intelligent default answer if the user skips this question. Make it a reasonable assumption for a premium Indian sanitaryware brand.
- "context": A brief note (1 sentence) explaining why this matters (shown as hint text)

Rules:
- Maximum 8 questions total
- Prioritize high-importance gaps first
- Make questions practical and easy to answer
- Default values should be sensible for a premium sanitaryware brand (Ruva)
- Keep language simple and non-technical

Return a valid JSON array of question objects."""

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL_ANALYSIS,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            cost = _extract_cost(response, MODEL_ANALYSIS)
            cost["operation"] = "Question Generation"

            questions = _parse_json_response(response.text)
            if isinstance(questions, list):
                return questions, cost
            # Sometimes Gemini wraps in {"questions": [...]}
            if isinstance(questions, dict) and "questions" in questions:
                return questions["questions"], cost
            return [], cost
        except Exception as e:
            print(f"[GEMINI] questions attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                time.sleep(2)

    # Fallback: generate basic questions from gaps
    fallback = []
    for gap in gaps[:8]:
        fallback.append({
            "id": gap["id"],
            "text": f"Could you provide details about: {gap['description']}?",
            "type": "text",
            "options": None,
            "default_value": "Premium quality, standard specifications",
            "context": f"This was found in the competitor's catalog ({gap['category']}).",
        })
    return fallback, {"model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "cost_inr": 0, "operation": "Question Generation"}
