import os
from dotenv import load_dotenv

load_dotenv()

# API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Gemini model names
MODEL_ANALYSIS = "gemini-3.1-flash-image-preview"
MODEL_IMAGE_PRIMARY = "gemini-3-pro-image-preview"
MODEL_IMAGE_FALLBACK = "gemini-2.5-flash-image"

# Directories
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

# Pricing per 1M tokens (USD) — from ai.google.dev/gemini-api/docs/pricing
PRICING = {
    "gemini-3.1-flash-image-preview": {"input": 0.50, "output": 60.00},
    "gemini-3-pro-image-preview": {"input": 2.00, "output": 120.00},
    "gemini-2.5-flash-image": {"input": 0.00, "output_per_image": 0.039},
}

# Currency conversion
USD_TO_INR = 85.0
