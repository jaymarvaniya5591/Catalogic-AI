"""
Gemini AI service — catalog analysis, gap detection, smart questions.
Uses the google-genai SDK (NOT the deprecated google-generativeai).
"""

import asyncio
import json
import time
import re
from pathlib import Path
from io import BytesIO

from PIL import Image
from typing import List, Optional, Literal
from pydantic import BaseModel
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, MODEL_ANALYSIS, MODEL_IMAGE_PRIMARY, MODEL_IMAGE_FALLBACK, PRICING, USD_TO_INR

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

MAX_IMAGE_BYTES = 10_000_000  # 10 MB (Gemini supports up to 20MB)


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

    # Last resort — preserve reasonable quality
    buf = BytesIO()
    img.resize((2048, 2048), Image.LANCZOS).save(buf, format=fmt, quality=85)
    return buf.getvalue()


def _parse_json_response(text: str):
    """Parse JSON from Gemini response, stripping markdown fences and handling extra text."""
    cleaned = text.strip()
    # Strip ```json ... ``` wrapper
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start_brace = cleaned.find('{')
    start_bracket = cleaned.find('[')
    end_brace = cleaned.rfind('}')
    end_bracket = cleaned.rfind(']')

    start_idx = -1
    if start_brace != -1 and start_bracket != -1:
        start_idx = min(start_brace, start_bracket)
    elif start_brace != -1:
        start_idx = start_brace
    elif start_bracket != -1:
        start_idx = start_bracket

    end_idx = -1
    if end_brace != -1 and end_bracket != -1:
        end_idx = max(end_brace, end_bracket)
    elif end_brace != -1:
        end_idx = end_brace
    elif end_bracket != -1:
        end_idx = end_bracket

    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        cleaned = cleaned[start_idx:end_idx+1]

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


# ── Product Category Detection ──

async def detect_product_category(
    title: str,
    description: str,
    features: list[str],
) -> tuple[dict, dict]:
    """
    Detect the product category from scraped title/description/features.
    Returns (category_info_dict, cost_info).
    """
    client = get_client()
    features_text = "\n".join(f"- {f}" for f in (features or [])[:20])

    prompt = f"""Analyze this product listing and determine the product category.

Product title: {title}

Product description:
{description[:1500] if description else 'Not available'}

Product features:
{features_text or 'Not available'}

Return a JSON object with:
1. "category": The broad product category (e.g., "perfume", "sanitaryware", "cookware", "electronics", "furniture", "clothing", "skincare", "toys", etc.)
2. "subcategory": The specific product type (e.g., "eau de parfum", "toilet/WC", "non-stick pan", "wireless earbuds")
3. "relevant_attributes": Array of 8-15 product attributes relevant for this category. Each with:
   - "attribute_id": snake_case identifier
   - "label": Human-readable label
   - "answer_type": "text", "choice", or "image"
   - "typical_options": Array of 3-5 common options (for choice type, otherwise empty array)
4. "environment_suggestion": A 1-2 sentence description of the ideal premium photography environment for this product category (e.g., "Dark marble surface with warm amber backlight and subtle smoke wisps" for perfume, "Modern marble bathroom with soft natural daylight" for sanitaryware)
5. "attribute_families": Object mapping family names to arrays of related attribute_ids that should be grouped together (knowing one suppresses questions about others in same family)
6. "ocr_keywords": Object mapping family names to arrays of keywords that indicate the attribute is already provided in OCR text

Return ONLY valid JSON, no markdown."""

    for attempt in range(2):
        try:
            response = await client.aio.models.generate_content(
                model=MODEL_ANALYSIS,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            cost = _extract_cost(response, MODEL_ANALYSIS)
            cost["operation"] = "Category Detection"
            result = _parse_json_response(response.text)
            return result, cost
        except Exception as e:
            if attempt == 0:
                continue
            print(f"[GEMINI] Category detection failed: {e}")
            # Return a generic fallback
            return {
                "category": "consumer product",
                "subcategory": "general",
                "relevant_attributes": [],
                "environment_suggestion": "Clean, modern studio with soft natural lighting",
                "attribute_families": {},
                "ocr_keywords": {},
            }, {"model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0, "cost_inr": 0, "operation": "Category Detection (fallback)"}


class Claim(BaseModel):
    attribute_id: str
    label: str
    value: str
    answer_type: Literal["text", "choice", "image"]
    options: Optional[List[str]] = None
    confidence: float
    evidence_text: str

class ImageAnalysis(BaseModel):
    index: int
    type: str
    intent: str
    summary: str
    key_elements: List[str]
    priority: str
    style_prompt: str
    visible_text_snippets: List[str]
    claims: List[Claim]

class RequiredClaim(BaseModel):
    attribute_id: str
    label: str
    value: str
    answer_type: Literal["text", "choice", "image"]
    options: Optional[List[str]] = None
    confidence: float
    evidence_text: str

class SuggestedAddition(BaseModel):
    id: str
    title: str
    category: str
    required_claims: List[RequiredClaim]
    generation_prompt_fragment: str

class CatalogAnalysisResponse(BaseModel):
    images: List[ImageAnalysis]
    catalog_strategy: str
    recommended_order: List[int]
    suggested_additions: List[SuggestedAddition]

# ── Function 1: Analyze Competitor Catalog ──

async def analyze_competitor_catalog(images: list[str], description: str, product_category: str = "", product_subcategory: str = "") -> tuple[dict, dict]:
    """
    Send all competitor images + description to Gemini.
    Returns (analysis_result, cost_info).
    """
    n = len(images)
    client = get_client()
    category_label = f"{product_category}/{product_subcategory}" if product_category else "consumer products"

    prompt = f"""You are a professional e-commerce catalog analyst for {category_label} products.

I'm showing you {n} catalog images from a competitor product listing, along with the product description.

Product description:
{description}

Task A — Per-image catalog intent & style:
For each image (numbered 0 through {n - 1}), identify:
1. "type": The image category. Must be one of: "hero", "lifestyle", "closeup", "dimensions", "infographic", "comparison", "packaging", "installation", "features", "brand", "other"
2. "intent": A short description (1-2 sentences) of what this image communicates to the buyer
3. "summary": A detailed 2-3 sentence summary of EVERYTHING visible in this image — exact product color/finish, all text (OCR), every specification, every measurement, every diagram element, every label, every callout, background/setting details. Describe with maximum detail.
4. "key_elements": List of visual elements present (e.g. ["bathroom setting", "marble countertop", "warm lighting"])
5. "priority": "high", "medium", or "low" — how important this image type is for a catalog
6. "style_prompt": A detailed 3-5 sentence description of what this catalog image communicates and HOW it does so visually. Structure it as:
   - Composition type: single hero shot / multi-view diagram / infographic with callouts / cross-section / lifestyle / dimensions diagram / feature highlight
   - EXACT number of product views shown and their arrangement (e.g., "4 views arranged in 2x2 grid: top-left is top view, top-right is bottom view, bottom-left is side view, bottom-right is back view")
   - Text placement style and typography approach (font color, overlay style, heading vs body)
   - Background treatment, lighting mood, camera angle(s)
   - Information hierarchy (what's most prominent vs supporting)
   Be specific enough that someone could recreate the EXACT SAME LAYOUT for a completely different product. Do NOT include actual product specs — focus on the visual storytelling approach and structure.

Task B — OCR-style extraction + factual product claims visible in each image:
From each image, do two things:
1) Extract verbatim visible text snippets (OCR):
- Output "visible_text_snippets": a list of short snippets (max 10), each snippet should be a verbatim fragment from the image that contains technical or specification text (flush/trap/outlet/rough-in/dimensions/ratings/etc.).
2) Extract structured claims:
From the same image, extract all technical or product attribute information that is explicitly communicated (on-image text, icons, diagrams, labeled parts, measurements, callouts, etc.).
For each extracted claim output:
- "attribute_id": stable snake_case id relevant to this product category (e.g., dimensions, material_finish, product_color, weight, key features specific to this product type)
- "label": human readable label (short)
- "value": the value shown in the image (verbatim if possible, otherwise normalized)
- "answer_type": one of: "text", "choice", or "image"
- If answer_type is "choice", also provide "options" (3-5 options) that are plausible choices for this product category; ensure the competitor's "value" is included in options.
- "confidence": number 0-1 (how confident you are that value is correct from the image)
- "evidence_text": short snippet of what you see (max ~20 words). If you cannot quote, set to "".

Only output claims with confidence >= 0.25. If text exists but you're unsure, still output a claim with lower confidence and best-effort value.

Task C — Suggested missing images (additions):
Study all images + the full provided product description text and infer whether there are vital catalog messages missing from the competitor images. Use the scraped text AND the complete pool of info from all images to identify at most 2 meaningful images the competitor didn't cover that would be important for a complete, premium A+ grade catalog listing.
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
      "summary": "...",
      "key_elements": [...],
      "priority": "...",
      "style_prompt": "...",
      "visible_text_snippets": [...],
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
            response = await client.aio.models.generate_content(
                model=MODEL_ANALYSIS,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CatalogAnalysisResponse,
                ),
            )
            result = _parse_json_response(response.text)
            cost = _extract_cost(response, MODEL_ANALYSIS)
            cost["operation"] = "Catalog Analysis"
            return result, cost
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GEMINI] analyze attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(2)

    # Fallback: return generic structure (no claims / no additions)
    fallback = {
        "images": [
            {
                "index": i,
                "type": "other",
                "intent": "Could not analyze",
                "summary": "",
                "key_elements": [],
                "priority": "medium",
                "style_prompt": "",
                "visible_text_snippets": [],
                "claims": [],
            }
            for i in range(n)
        ],
        "catalog_strategy": "Analysis unavailable.",
        "recommended_order": list(range(n)),
        "suggested_additions": [],
    }
    return fallback, {"model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "cost_inr": 0, "operation": "Catalog Analysis"}


# ── Function 1b: Analyze User Product Images ──

class UserExtractedAttribute(BaseModel):
    attribute_id: str
    value: str
    confidence: float
    evidence_text: str

class UserImageSummary(BaseModel):
    index: int
    description: str
    detected_text: List[str]

class UserImageAnalysisResponse(BaseModel):
    extracted_attributes: List[UserExtractedAttribute]
    image_summaries: List[UserImageSummary]

DEFAULT_CANONICAL_ATTRIBUTE_IDS = (
    "dimensions, material_finish, product_color, product_weight, "
    "warranty_years, certification, installation_type"
)

async def analyze_user_product_images(
    images: list[str],
    product_description: str,
    canonical_attributes: str = "",
) -> tuple[dict, dict]:
    """
    Analyze user's own product images via Gemini to extract attributes already visible.
    Returns (user_analysis_dict, cost_info).
    """
    if not images:
        return {"extracted_attributes": [], "image_summaries": []}, {
            "model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0, "cost_inr": 0, "operation": "User Image Analysis",
        }

    n = len(images)
    client = get_client()

    prompt = f"""You are analyzing {n} product images uploaded by the user (the product owner, NOT a competitor).

Your goal is to extract ALL factual information visible in these images about the product.

Product description from user:
{product_description}

For EACH image, examine with maximum detail:
- Exact product color and finish (e.g., glossy white, matte black, ivory)
- All text visible via OCR (labels, specifications, dimensions, model numbers)
- Any dimension diagrams or measurements (height, width, depth, rough-in distance)
- Material appearance (ceramic, porcelain, etc.)
- Product features visible (specific to this product category)
- Installation details, packaging info, certifications

Return structured JSON with:

1. "extracted_attributes": A list of all product attributes you can confidently extract.
   Use these canonical attribute_ids where applicable: {canonical_attributes or DEFAULT_CANONICAL_ATTRIBUTE_IDS}
   Each attribute:
   - "attribute_id": snake_case id (use canonical ids above when possible)
   - "value": the extracted value
   - "confidence": 0-1 (how confident you are)
   - "evidence_text": brief quote/description of what you see (max 20 words)
   Only include attributes with confidence >= 0.2.

2. "image_summaries": For each image (indexed 0 to {n - 1}):
   - "index": image index
   - "description": Detailed description of everything visible in this image
   - "detected_text": List of all text strings detected via OCR

Return valid JSON matching this structure exactly."""

    contents: list = [prompt]
    for img_path in images[:5]:
        try:
            contents.append(_load_image_for_gemini(img_path))
        except FileNotFoundError as e:
            print(f"[GEMINI] Skipping missing user image: {e}")

    for attempt in range(2):
        try:
            response = await client.aio.models.generate_content(
                model=MODEL_ANALYSIS,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=UserImageAnalysisResponse,
                ),
            )
            result = _parse_json_response(response.text)
            cost = _extract_cost(response, MODEL_ANALYSIS)
            cost["operation"] = "User Image Analysis"
            return result, cost
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GEMINI] user image analysis attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(2)

    return {"extracted_attributes": [], "image_summaries": []}, {
        "model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0,
        "cost_usd": 0, "cost_inr": 0, "operation": "User Image Analysis",
    }


# ── Master Context Block Generation ──

async def generate_master_context_block(
    product_images: list[str],
    product_description: str,
    compiled_attributes: dict,
    product_category: str = "",
) -> tuple[str, dict]:
    """
    Generate a rich, reusable master context block that describes the product
    and photography style in detail. This replaces dry key-value attributes
    with natural-language prose that produces far better image generation results.

    Works for ANY product category — the model determines the appropriate
    environment and photography style based on the product type.

    Returns (master_context_text, cost_info).
    """
    client = get_client()
    attributes_text = _attributes_to_text(compiled_attributes)
    category_hint = f"\nProduct category: {product_category}" if product_category else ""

    prompt = f"""You are a professional product photographer and catalog designer.
I'm giving you reference images of a product and its description. Your job is to create a detailed
MASTER CONTEXT BLOCK that will be reused across multiple image generation prompts to ensure consistency.

Product description:
{product_description}{category_hint}

Known technical attributes:
{attributes_text}

Generate THREE sections:

SECTION A — PRODUCT LOCKED SPECS:
Write a dense, visual, natural-language description of the product (~200 words). Cover:
- Exact product type and category
- Brand name (if visible or mentioned)
- Shape, form factor, silhouette — describe with precision (e.g., "elongated oval bowl, smooth curved body")
- Color, finish, surface texture (e.g., "glossy pure white ceramic, high-gloss, mirror-like surface sheen")
- Material and construction details
- Key design features visible in the images
- Proportions and dimensional relationships between parts
- Any buttons, handles, mechanisms, or functional elements
- Base/mounting style

Study the reference images carefully and describe what you SEE, not what you assume.
Use the technical attributes to add precision, but always prioritize visual accuracy from the images.

SECTION B — PHOTOGRAPHY STYLE LOCKED:
Based on the product category, determine the ideal premium photography environment and write locked style parameters:
- Rendering style (always: "Hyperrealistic photographic rendering — NOT illustrative, NOT cartoon, NOT 3D render")
- Lighting (natural soft daylight, warm morning/afternoon light — specify exact direction e.g. "from upper-left at 45 degrees")
- Environment/setting appropriate for this product category (e.g., marble bathroom for sanitaryware, modern kitchen for cookware, elegant bedroom for bedding, studio for electronics) — be VERY specific about wall material/color, floor material/color, and ambient elements
- Camera style (DSLR-quality depth of field, sharp product focus)
- Color grading (warm, premium, aspirational)
- Aspect ratio: 1:1 square
- SINGLE PRODUCT ONLY: Every image must show exactly ONE product unit — never duplicate, mirror, or show multiple copies of the product
- What to exclude (no text, no watermarks, no logos unless generating infographic)

SECTION C — TYPOGRAPHY LOCKED (for infographic/diagram images):
Define a premium typography system that ALL text-containing catalog images MUST follow identically:
- Font: Thin/light-weight elegant sans-serif (like Montserrat Light, Lato Light, or SF Pro Display Thin) — NOT bold, NOT heavy
- Headings: Thin uppercase sans-serif, generous letter-spacing (tracking), centered/symmetric placement
- Body/label text: Light weight, same font family, slightly smaller
- Color scheme: White or warm off-white (#F5F0E8) text. For dark backgrounds use white; for light backgrounds use charcoal (#2A2A2A)
- Accent: Subtle warm gold/amber (#C4A265) for divider lines, callout connectors, or highlight borders — used sparingly
- Callout lines: Thin (1-2px), straight, connecting product features to labels — elegant, not cluttered
- Icons: Minimal line-art style, monochrome, matching text color — NOT colorful, NOT filled/heavy
- Layout: Symmetric and balanced — headings centered, callouts evenly distributed, equal spacing
- ALL infographic images MUST use this IDENTICAL typography — same font weight, same colors, same icon style

Format your output EXACTLY like this (plain text, not JSON):

PRODUCT LOCKED SPECS:
[Your detailed product description here]

PHOTOGRAPHY STYLE LOCKED:
- [Style parameter 1]
- [Style parameter 2]
- [etc.]

TYPOGRAPHY LOCKED:
- Font: [thin/light-weight sans-serif family]
- Headings: [UPPERCASE, thin weight, letter-spacing, placement]
- Text color: [color values for dark/light backgrounds]
- Accent color: [warm gold/amber value and usage rule]
- Callout lines: [weight, style]
- Icons: [style — line-art, monochrome]
- Layout: [symmetric/balanced rules]
"""

    contents: list = [prompt]
    for img_url in (product_images or [])[:3]:
        try:
            contents.append(_load_image_for_gemini(img_url))
        except Exception:
            continue

    for attempt in range(2):
        try:
            response = await client.aio.models.generate_content(
                model=MODEL_ANALYSIS,
                contents=contents,
            )
            cost = _extract_cost(response, MODEL_ANALYSIS)
            cost["operation"] = "Master Context Generation"

            master_context = response.text.strip()
            if master_context:
                return master_context, cost
            raise RuntimeError("Empty master context response")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GEMINI] master context attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(2)

    # Fallback: build a basic context from attributes
    fallback = f"""PRODUCT LOCKED SPECS:
{product_description}

Technical attributes:
{attributes_text}

PHOTOGRAPHY STYLE LOCKED:
- Hyperrealistic photographic rendering — NOT illustrative, NOT cartoon, NOT 3D render
- Natural soft daylight — warm morning/afternoon light from a window
- Premium setting appropriate for this product category
- Camera: DSLR-quality depth of field — sharp product, gentle background blur
- Aspect ratio: 1:1 square
- NO text, NO watermarks, NO logos unless explicitly generating an infographic
"""
    return fallback, {
        "model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0,
        "cost_usd": 0, "cost_inr": 0, "operation": "Master Context Generation (fallback)",
    }


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


class Question(BaseModel):
    id: str
    text: str
    type: Literal["text", "choice", "image"]
    options: Optional[List[str]] = None
    default_value: str
    context: str

# ── Function 3: Generate Smart Questions ──

async def generate_smart_questions(gaps: list[dict], analysis: dict, product_category: str = "") -> tuple[list[dict], dict]:
    """
    Turn information gaps into user-friendly questions with intelligent defaults.
    Returns (questions_list, cost_info).
    """
    if not gaps:
        return [], {"model": MODEL_ANALYSIS, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0, "cost_inr": 0, "operation": "Question Generation"}

    client = get_client()
    strategy = analysis.get("catalog_strategy", "No strategy available.")
    category_label = product_category or "consumer product"

    prompt = f"""You are helping a premium Indian brand create catalog images for their {category_label} product.
Based on the information gaps identified below, generate smart questions for the user.

Gaps found:
{json.dumps(gaps, indent=2)}

Competitor catalog strategy: {strategy}

For each gap, generate a question with:
- "id": same as the gap id
- "text": A clear, friendly question (1-2 sentences max)
- "type": "text" (free text answer), "choice" (multiple choice), or "image" (user uploads an image)
- "options": If type is "choice", provide 3-5 options as a list. Otherwise null.
- "default_value": An intelligent default answer if the user skips this question. Make it a reasonable assumption for a premium {category_label} product.
- "context": A brief note (1 sentence) explaining why this matters (shown as hint text)

Rules:
- Maximum 8 questions total
- Prioritize high-importance gaps first
- Make questions practical and easy to answer
- Default values should be sensible for a premium {category_label} brand
- Keep language simple and non-technical

Return a valid JSON array of question objects."""

    for attempt in range(2):
        try:
            response = await client.aio.models.generate_content(
                model=MODEL_ANALYSIS,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=list[Question],
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
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GEMINI] questions attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(2)

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
        label = k.replace("_", " ").title()
        if isinstance(v, str) and _is_upload_image_url(v):
            lines.append(f"- {label}: [see reference image]")
        else:
            lines.append(f"- {label}: {v}")
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


async def generate_hero_image(
    session_id: str,
    product_images: list[str],
    product_description: str,
    compiled_attributes: dict,
    master_context: str = "",
) -> tuple[str, dict]:
    """
    Generate a hero image and save it under outputs/{session_id}/hero/hero.png.
    Returns (hero_url, cost_info).
    """
    client = get_client()
    out_path = Path("outputs") / session_id / "hero" / "hero.png"

    reference_images = (product_images or [])[:3]

    # Use master context if available, otherwise fall back to attributes
    context_block = master_context if master_context else f"""Product description:
{product_description}

Technical attributes:
{_attributes_to_text(compiled_attributes)}
"""

    prompt = f"""Generate ONE hyperrealistic photograph of this product as the HERO catalog image.
This is the VISUAL ANCHOR — all other catalog images will reference this for consistent product appearance.

{context_block}

CRITICAL REQUIREMENTS:
- The product must be the SOLE subject — exactly ONE product unit, never duplicated or mirrored
- Placed in a premium environment appropriate for this product category (the master context defines the exact environment)
- Warm natural daylight streaming from the left side at ~45 degrees, creating subtle soft shadows on the right
- Hyperrealistic PHOTOGRAPH — NOT a 3D render, NOT an illustration, NOT CGI
- DSLR-quality: sharp focus on the product, gentle depth-of-field blur on the background
- Camera angle: 3/4 front view, slightly elevated — showing the product's best angle with full dimensionality
- Full product visible with ~10% breathing room on all sides
- Amazon A+ listing quality — top 0.01% of product images in this category
- NO text, NO watermarks, NO branding, NO logos anywhere in the image
- NOTE: The reference product images provided may contain watermarks or brand overlays — IGNORE them entirely; reproduce only the physical product shape, color, and design details

PRODUCT FIDELITY (MOST IMPORTANT):
- Study the reference product images PIXEL BY PIXEL before generating
- The generated product must be INDISTINGUISHABLE from the reference — same exact silhouette, same proportions, same design language
- Reproduce EVERY detail: exact shape, proportions, design language, surface finish, functional elements, hardware placement, edge treatments
- If the reference shows a specific ratio between parts (e.g., component proportions), maintain that EXACT ratio
- If the reference shows rounded corners vs sharp corners, curved vs angular surfaces — match it precisely
- DO NOT use a generic product shape. The reference images ARE the ground truth
- Common mistakes to AVOID: wrong proportions, generic/default shapes, missing or altered design details, different hardware/buttons, smoothing over distinctive features
- The viewer should look at the generated image and the reference and believe they are the SAME physical product photographed in a different setting
"""

    contents: list = [prompt]
    for img_url in reference_images:
        contents.append(_load_image_for_gemini(img_url))

    contents.extend(_collect_answer_image_parts(compiled_attributes))

    last_err = None
    for attempt_model in [MODEL_IMAGE_PRIMARY, MODEL_IMAGE_FALLBACK]:
        # Try with higher resolution first, fall back if model rejects image_size
        for img_config in [
            types.ImageConfig(aspect_ratio="1:1", image_size="2K"),
            types.ImageConfig(aspect_ratio="1:1"),
        ]:
            try:
                response = await client.aio.models.generate_content(
                    model=attempt_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=img_config,
                    ),
                )
                cost = _extract_cost(response, attempt_model)
                cost["operation"] = "Hero Image Generation"

                ok = _save_generated_image(out_path, response)
                if not ok:
                    raise RuntimeError("Hero generation returned no image part")

                hero_url = f"/outputs/{session_id}/hero/hero.png"
                return hero_url, cost
            except Exception as e:
                err_str = str(e).lower()
                if "image_size" in err_str or "image size" in err_str:
                    print(f"[GEMINI] image_size not supported by {attempt_model}, retrying without it")
                    continue  # try without image_size
                last_err = e
                break  # move to fallback model

    raise RuntimeError(f"Hero generation failed: {type(last_err).__name__}: {last_err}")


async def generate_catalog_image(
    session_id: str,
    image_key: str,
    hero_image_url: str,
    reference_intent_image_url: str | None,
    style_prompt: str,
    prompt_fragment: str,
    compiled_attributes: dict,
    changed_attributes: dict | None = None,
    master_context: str = "",
) -> tuple[str, dict]:
    """
    Generate a catalog image and save it under outputs/{session_id}/catalog/{image_key}.png.
    Returns (image_url, cost_info).
    """
    client = get_client()
    out_path = Path("outputs") / session_id / "catalog" / f"{image_key}.png"

    attributes_text = _attributes_to_text(compiled_attributes)

    changed_section = ""
    if changed_attributes:
        changed_lines = [f"- {k}: {v}" for k, v in changed_attributes.items()]
        changed_section = f"""
IMPORTANT — The following attributes DIFFER from the competitor image and must be reflected in the generated image:
{chr(10).join(changed_lines)}
For all other attributes, match the competitor image's approach and visual style."""
    else:
        changed_section = "Match all attributes from the competitor image's approach, using this product's appearance from the HERO image."

    # Use master context if available, otherwise fall back to attributes
    context_block = master_context if master_context else f"""Technical attributes:
{attributes_text}
"""

    # Environment override — ALL catalog images must use the hero's environment,
    # never the competitor's. This is critical because competitor images often have
    # very distinct settings (teal walls, coloured tiles) that Gemini tends to copy.
    hero_env_override = ""
    if reference_intent_image_url:
        hero_env_override = """
ENVIRONMENT OVERRIDE (ABSOLUTE RULE — applies to every catalog image):
- The background, walls, floor, and lighting MUST match IMAGE 1 (HERO) exactly
- COMPLETELY IGNORE the environment/setting shown in Image 2 (competitor) — treat their walls, floor, tiles, background colour, and props as if they were invisible
- Do NOT copy ANY part of the competitor's room, bathroom, tiles, wall colour, floor material, or props — not even subtly
- Use ONLY the environment, wall colour/material, floor, and lighting from Image 1 (HERO)
- Image 2 is a reference ONLY for composition purpose and layout — NEVER for environment or background
"""

    # Build the image reference instructions based on what we have
    if reference_intent_image_url:
        image_ref_block = """You are given TWO reference images:
- IMAGE 1 (HERO): This is the PRODUCT VISUAL ANCHOR. The generated image must show this EXACT product — same shape, color, proportions, design details, and surface finish.
- IMAGE 2 (COMPETITOR INTENT): This shows what this catalog slot needs to COMMUNICATE — the purpose, composition, information, and visual story. Recreate the SAME PURPOSE for our product from Image 1."""
    else:
        image_ref_block = """You are given ONE reference image:
- IMAGE 1 (HERO): This is the PRODUCT VISUAL ANCHOR. The generated image must show this EXACT product — same shape, color, proportions, design details, and surface finish.
Use the slot instructions below to determine what this catalog image should communicate."""

    prompt = f"""Generate ONE catalog image for an Amazon A+ product listing.

{image_ref_block}

{context_block}

WHAT THIS IMAGE MUST COMMUNICATE:
{style_prompt}

DETAILED REFERENCE:
{prompt_fragment}

{changed_section}

{hero_env_override}

{"LAYOUT MATCHING (CRITICAL):" if reference_intent_image_url else ""}
{"- Match the EXACT layout structure of Image 2: same number of views/panels, same arrangement, same information hierarchy" if reference_intent_image_url else ""}
{"- If Image 2 shows 2 views, generate EXACTLY 2 views. If it shows 4 views, generate EXACTLY 4. Count carefully." if reference_intent_image_url else ""}
{"- Recreate the SAME visual storytelling approach — same composition type, same information flow" if reference_intent_image_url else ""}

PRODUCT FIDELITY (CRITICAL):
- The product in this image must be IDENTICAL to Image 1 (HERO) — not just similar, IDENTICAL
- Same exact shape, silhouette, proportions, surface finish, color, texture, and every visible design detail
- If the HERO shows a specific tank-to-bowl ratio, button style, handle shape, or base profile — reproduce it EXACTLY
- DO NOT substitute a generic product shape. The HERO image IS the ground truth for product appearance
- Common mistakes to AVOID: wrong proportions, generic shapes, missing design details, different hardware

SINGLE PRODUCT RULE:
- Show EXACTLY ONE product unit in this image — never duplicate, mirror, or show multiple copies of the product

FUNCTIONAL DIAGRAMS (if applicable):
- If {"Image 2 shows" if reference_intent_image_url else "this slot requires"} a FUNCTIONAL DIAGRAM (mechanism cross-section, internal working, cutaway view, technical visualization):
  You MUST show the same functional visualization with clear arrows, flow indicators, cross-section views, or cutaway renders that explain HOW the product/mechanism works
  The visualization must be technically informative and prominent, not just decorative
  Use appropriate color coding for flows/indicators, directional arrows for movement, labels for key components

TYPOGRAPHY (ABSOLUTE RULE — for ALL images with any text, callouts, or labels):
- DO NOT copy fonts, font weight, text style, or text colour from Image 2 (competitor) — their typography is irrelevant and must be completely ignored
- Font: Thin/light-weight elegant sans-serif (Montserrat Light / Lato Light style) — NOT bold, NOT heavy, NOT the competitor's style
- Headings: UPPERCASE, thin weight, generous letter-spacing, centered symmetrically at top
- Body/label text: Light weight, same font family, clean and minimal
- Text color: White or warm off-white (#F5F0E8) on dark overlays; charcoal (#2A2A2A) on light backgrounds
- Accent color: Warm gold/amber (#C4A265) — use ONLY for thin divider lines, callout connector lines, or subtle highlight borders
- Callout lines: Thin (1-2px), straight, elegant — connecting product features to their labels
- Icons: Minimal line-art, monochrome, matching text color — NOT colorful emoji-style, NOT heavy filled icons
- Layout: SYMMETRIC and balanced — even spacing, centered headings, evenly distributed callouts on left/right
- This typography MUST match ALL other infographic images in this catalog — identical font, weight, colors, icon style

WATERMARK & BRANDING WARNING (ABSOLUTE RULE):
- Image 2 (the competitor reference) likely contains a brand watermark, logo, or diagonal text overlay (e.g., brand name printed across the image)
- You MUST completely IGNORE any watermarks, brand names, logos, or overlay text you see in Image 2
- NEVER reproduce, copy, or include any such marks in the generated image
- The final image must be 100% watermark-free and brand-neutral — no text from Image 2 should appear anywhere

QUALITY STANDARDS:
- Hyperrealistic PHOTOGRAPH — NOT an illustration, NOT a 3D render, NOT CGI
- DSLR-quality depth of field, warm natural lighting
- Aspect ratio: 1:1 square
- Amazon A+ listing quality — top 0.01% of product images
- ABSOLUTELY NO watermarks, brand names, logos, or overlay text — treat any marks seen in reference images as invisible
- If you lack exact data for text/numbers shown in the reference, use the product attributes provided above — do NOT invent specifications
"""

    contents: list = [prompt, _load_image_for_gemini(hero_image_url)]
    if reference_intent_image_url:
        contents.append(_load_image_for_gemini(reference_intent_image_url))

    contents.extend(_collect_answer_image_parts(compiled_attributes))

    last_err = None
    for attempt_model in [MODEL_IMAGE_PRIMARY, MODEL_IMAGE_FALLBACK]:
        for img_config in [
            types.ImageConfig(aspect_ratio="1:1", image_size="2K"),
            types.ImageConfig(aspect_ratio="1:1"),
        ]:
            try:
                response = await client.aio.models.generate_content(
                    model=attempt_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=img_config,
                    ),
                )
                cost = _extract_cost(response, attempt_model)
                cost["operation"] = "Catalog Image Generation"

                ok = _save_generated_image(out_path, response)
                if not ok:
                    raise RuntimeError("Catalog generation returned no image part")

                image_url = f"/outputs/{session_id}/catalog/{image_key}.png"
                return image_url, cost
            except Exception as e:
                err_str = str(e).lower()
                if "image_size" in err_str or "image size" in err_str:
                    print(f"[GEMINI] image_size not supported by {attempt_model}, retrying without it")
                    continue
                last_err = e
                break

    raise RuntimeError(f"Catalog generation failed: {type(last_err).__name__}: {last_err}")
