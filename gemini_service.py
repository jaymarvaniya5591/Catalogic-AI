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

    prompt = f"""You are a professional e-commerce catalog analyst for sanitaryware/bathroom products (toilets, WCs, flush systems).

I'm showing you {n} catalog images from a competitor product listing, along with the product description.

Product description:
{description}

Task A — Per-image catalog intent & style:
For each image (numbered 0 through {n - 1}), identify:
1. "type": The image category. Must be one of: "hero", "lifestyle", "closeup", "dimensions", "infographic", "comparison", "packaging", "installation", "features", "brand", "other"
2. "intent": A short description (1-2 sentences) of what this image communicates to the buyer
3. "key_elements": List of visual elements present (e.g. ["bathroom setting", "marble countertop", "warm lighting"])
4. "priority": "high", "medium", or "low" — how important this image type is for a catalog
5. "style_prompt": A short reusable prompt fragment (1-2 sentences) describing the visual style/messages for this image type (NOT the actual product specs).

Task B — Extract factual product claims visible in each image:
From each image, extract all technical or product attribute information that is explicitly communicated (on-image text, icons, diagrams, labeled parts, measurements, callouts, etc.).
For each extracted claim output:
- "attribute_id": stable snake_case id (examples: flush_system_type, trap_outlet_type, s_trap_or_p_trap, rough_in_inches, rim_type, bumper_design, dimensions, material_finish, flush_method, water_tank_compatibility)
- "label": human readable label (short)
- "value": the value shown in the image (verbatim if possible, otherwise normalized)
- "answer_type": one of: "text", "choice", or "image"
- If answer_type is "choice", also provide "options" (3-5 options) that are plausible sanitaryware choices; ensure the competitor's "value" is included in options.
- "confidence": number 0-1 (how confident you are that value is correct from the image)
- "evidence_text": short snippet of what you see (max ~20 words). If you cannot quote, set to "".

Only output claims with confidence >= 0.55. If uncertain, omit the claim.

Task C — Suggested missing images (additions):
Study all images + the provided product description and infer whether there are vital catalog messages missing from the competitor images.
You may suggest up to 2 additions.
Each suggested addition must include:
- "id", "title", "category"
- "required_claims": up to 3 claim objects (same structure as Task B but without needing to be directly visible in competitor images; infer the most likely values using competitor images/description; confidence >= 0.5)
- "generation_prompt_fragment": 2-3 sentences describing what this missing catalog image should communicate visually and the messaging/diagram/text style.

Return valid JSON with this exact structure:
{{
  "images": [
    {{
      "index": 0,
      "type": "...",
      "intent": "...",
      "key_elements": [...],
      "priority": "...",
      "style_prompt": "...",
      "claims": [
        {{
          "attribute_id": "...",
          "label": "...",
          "value": "...",
          "answer_type": "text" | "choice" | "image",
          "options": null | [...],
          "confidence": 0.0,
          "evidence_text": "..."
        }}
      ]
    }},
    ...
  ],
  "catalog_strategy": "...",
  "recommended_order": [0, 2, 1, ...],
  "suggested_additions": [
    {{
      "id": "...",
      "title": "...",
      "category": "...",
      "required_claims": [
        {{
          "attribute_id": "...",
          "label": "...",
          "value": "...",
          "answer_type": "text" | "choice" | "image",
          "options": null | [...],
          "confidence": 0.0,
          "evidence_text": "..."
        }}
      ],
      "generation_prompt_fragment": "..."
    }},
    ...
  ]
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

    # Fallback: return generic structure (no claims / no additions)
    fallback = {
        "images": [
            {
                "index": i,
                "type": "other",
                "intent": "Could not analyze",
                "key_elements": [],
                "priority": "medium",
                "style_prompt": "",
                "claims": [],
            }
            for i in range(n)
        ],
        "catalog_strategy": "Analysis unavailable.",
        "recommended_order": list(range(n)),
        "suggested_additions": [],
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


# ── Helpers for Image Generation ──

def _is_upload_image_url(url_or_path: str) -> bool:
    s = (url_or_path or "").strip().lower()
    return s.startswith("/uploads/") and any(s.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"])


def _extract_first_generated_image(response) -> Image.Image | None:
    """
    Extract the first generated image from a Gemini response.
    """
    try:
        for part in getattr(response, "parts", []) or []:
            if getattr(part, "inline_data", None) is not None:
                return part.as_image()
    except Exception:
        return None
    return None


def _save_generated_image(output_path: Path, response) -> bool:
    img = _extract_first_generated_image(response)
    if img is None:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    return True


def _attributes_to_text(compiled_attributes: dict) -> str:
    lines: list[str] = []
    for k, v in (compiled_attributes or {}).items():
        if isinstance(v, str) and _is_upload_image_url(v):
            lines.append(f"- {k}: [user_provided_image]")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _collect_answer_image_parts(compiled_attributes: dict) -> list[types.Part]:
    parts: list[types.Part] = []
    for _, v in (compiled_attributes or {}).items():
        if isinstance(v, str) and _is_upload_image_url(v):
            try:
                parts.append(_load_image_for_gemini(v))
            except Exception:
                continue
        if len(parts) >= 2:
            break
    return parts


def generate_hero_image(
    session_id: str,
    product_images: list[str],
    product_description: str,
    compiled_attributes: dict,
) -> tuple[str, dict]:
    """
    Generate a hero image and save it under outputs/{session_id}/hero/hero.png.
    Returns (hero_url, cost_info).
    """
    client = get_client()
    out_path = Path("outputs") / session_id / "hero" / "hero.png"

    reference_images = (product_images or [])[:3]

    prompt = f"""Create a premium white-background studio HERO product image for Ruva sanitaryware (toilet/WC).

Reference the provided product images for the exact shape, proportions, and visible design details.
Use a clean seamless white background, soft diffused lighting, minimal shadows, and a centered composition
with a subtle 3/4 angle. Ensure no text, no competitor branding, and no watermark.

Technical attributes to match (specs/feature values):
{_attributes_to_text(compiled_attributes)}

Product description context:
{product_description}
"""

    contents: list = [prompt]
    for img_url in reference_images:
        contents.append(_load_image_for_gemini(img_url))

    contents.extend(_collect_answer_image_parts(compiled_attributes))

    last_err = None
    for attempt_model in [MODEL_IMAGE_PRIMARY, MODEL_IMAGE_FALLBACK]:
        try:
            response = client.models.generate_content(
                model=attempt_model,
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            cost = _extract_cost(response, attempt_model)
            cost["operation"] = "Hero Image Generation"

            ok = _save_generated_image(out_path, response)
            if not ok:
                raise RuntimeError("Hero generation returned no image part")

            hero_url = f"/outputs/{session_id}/hero/hero.png"
            return hero_url, cost
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Hero generation failed: {type(last_err).__name__}: {last_err}")


def generate_catalog_image(
    session_id: str,
    image_key: str,
    hero_image_url: str,
    reference_intent_image_url: str | None,
    style_prompt: str,
    prompt_fragment: str,
    compiled_attributes: dict,
) -> tuple[str, dict]:
    """
    Generate a catalog image and save it under outputs/{session_id}/catalog/{image_key}.png.
    Returns (image_url, cost_info).
    """
    client = get_client()
    out_path = Path("outputs") / session_id / "catalog" / f"{image_key}.png"

    attributes_text = _attributes_to_text(compiled_attributes)

    prompt = f"""You are generating an e-commerce catalog image for Ruva.

Goal:
Recreate the competitor (or inferred) image INTENT and visual messaging for this catalog slot
while using the provided HERO image as the visual anchor.

Style cues:
{style_prompt}

Slot-specific instructions:
{prompt_fragment}

Technical attributes to match:
{attributes_text}

Rules:
- Keep lighting, angle, and product framing consistent with the HERO image.
- Do not copy competitor branding or add any logos/text.
- Output a realistic studio product photo (or diagram style only if the reference intent is diagram-based).
"""

    contents: list = [prompt, _load_image_for_gemini(hero_image_url)]
    if reference_intent_image_url:
        contents.append(_load_image_for_gemini(reference_intent_image_url))

    contents.extend(_collect_answer_image_parts(compiled_attributes))

    last_err = None
    for attempt_model in [MODEL_IMAGE_PRIMARY, MODEL_IMAGE_FALLBACK]:
        try:
            response = client.models.generate_content(
                model=attempt_model,
                contents=contents,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
            cost = _extract_cost(response, attempt_model)
            cost["operation"] = "Catalog Image Generation"

            ok = _save_generated_image(out_path, response)
            if not ok:
                raise RuntimeError("Catalog generation returned no image part")

            image_url = f"/outputs/{session_id}/catalog/{image_key}.png"
            return image_url, cost
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Catalog generation failed: {type(last_err).__name__}: {last_err}")
