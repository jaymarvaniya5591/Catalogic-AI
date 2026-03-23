import os

# API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Gemini model names
MODEL_ANALYSIS = "gemini-3.1-flash-image-preview"
MODEL_IMAGE_PRIMARY = "gemini-3-pro-image-preview"
MODEL_IMAGE_FALLBACK = "gemini-2.5-flash-image"

# Directories
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
