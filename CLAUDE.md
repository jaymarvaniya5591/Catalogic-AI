# Ruva Catalog Generator

## What this is
A tool that takes a competitor's Amazon/Flipkart product link + user's product images → generates a full, professional catalog image set. Built for Ruva (sanitaryware brand).

## Core approach (CRITICAL — read this first)
1. Scrape/upload competitor catalog images + description
2. Analyze intent behind each competitor image (via Gemini)
3. Identify information gaps → ask smart questions → apply intelligent defaults for skipped ones
4. Generate a HERO IMAGE as the visual anchor
5. For each catalog image: send hero image + competitor intent image → Gemini generates a matching image for our product
6. Result: complete, visually consistent catalog set

**Why this works:** The hero image ensures visual consistency across all generated images. The competitor image defines WHAT needs to be communicated (intent), not how the product looks.

## Tech stack
- **Backend**: Python + FastAPI (`server.py`, `gemini_service.py`, `scraper.py`, `config.py`)
- **Frontend**: Vanilla HTML/CSS/JS (`static/index.html`, `static/style.css`, `static/app.js`)
- **SDK**: `google-genai` (NOT the deprecated `google-generativeai`)
- **Scraping**: Playwright headless browser + manual upload fallback
- **Dependencies**: fastapi, uvicorn, google-genai, playwright, Pillow, python-multipart

## Gemini models (quality > price)
- **Understanding/Analysis**: `gemini-3.1-flash-image-preview` (Nano Banana 2) — catalog analysis, intent extraction, gap detection, smart questions, consistency validation
- **Image Generation (primary)**: `gemini-3-pro-image-preview` (Nano Banana Pro) — hero image + all catalog images, highest quality
- **Image Generation (fallback)**: `gemini-2.5-flash-image` (Nano Banana) — auto-fallback if Pro fails/rate-limited

## Design
- Dark premium theme inspired by FounderGPT
- Colors: `#141414` bg, `#1c1c1c` secondary, `#a09060` gold accent
- Font: Inter
- 800px max-width, centered, minimal, clean

## Key files
- `server.py` — FastAPI app, all API routes, session management (in-memory dict)
- `gemini_service.py` — ALL Gemini API interactions (analysis, gap detection, question gen, image gen)
- `scraper.py` — Playwright-based Amazon/Flipkart scraper with stealth settings
- `config.py` — API keys, model names, constants
- `static/index.html` — Single-page app with 5 steps
- `static/style.css` — Complete dark theme design system
- `static/app.js` — Frontend state machine, API calls, SSE handling

## API endpoints
- `POST /api/scrape` — scrape competitor URL
- `POST /api/upload-competitor` — manual competitor image upload
- `POST /api/upload-product` — user's product images + description
- `POST /api/analyze` — trigger analysis pipeline (returns analysis + questions)
- `POST /api/generate-hero` — generate hero image
- `GET /api/generate-catalog/stream` — SSE stream for catalog generation
- `POST /api/regenerate` — regenerate a single catalog image
- `GET /api/download/{session_id}` — download catalog as ZIP

## Execution plan
See `execution-plan.html` for the full phase breakdown with detailed tasks per phase.

## Brand
Company: Ruva
