# AI Catalog Generator

> Turn a competitor's Amazon/Flipkart listing into a complete, professional product catalog — automatically.

Built for **Ruva** (sanitaryware brand). Paste a competitor URL, upload your product images, and get a full catalog image set that matches top listing quality.

---

## How It Works

```
Competitor URL  →  Scrape images + description
                        ↓
              Gemini analyzes each image's intent
                        ↓
         Smart questions fill information gaps
                        ↓
              Generate a Hero Image (visual anchor)
                        ↓
    Hero + each competitor intent → full catalog set
```

The **Hero Image** is the key — it locks in the visual identity, so every generated image feels like it came from the same photoshoot.

---

## Features

- Scrapes Amazon and Flipkart product listings (Playwright, headless)
- Manual upload fallback if scraping is blocked
- Gemini analyzes intent behind each competitor image
- Asks targeted questions to fill info gaps — skip any for smart defaults
- Generates a Hero Image as the visual anchor
- Streams catalog generation in real-time (SSE)
- Download full catalog as a ZIP
- Dark premium UI (inspired by FounderGPT)

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python + FastAPI |
| Frontend | Vanilla HTML / CSS / JS |
| AI | Google Gemini (`google-genai` SDK) |
| Scraping | Playwright (headless browser) |
| Image Processing | Pillow |

### Gemini Models

| Role | Model |
|---|---|
| Analysis & understanding | `gemini-3.1-flash-image-preview` |
| Image generation (primary) | `gemini-3-pro-image-preview` |
| Image generation (fallback) | `gemini-2.5-flash-image` |

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browser

```bash
python -m playwright install chromium
```

### 4. Set your Gemini API key

Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
```

Then edit `.env`:

```
GEMINI_API_KEY=your_key_here
```

Get a key at [Google AI Studio](https://aistudio.google.com/).

### 5. Run the server

```bash
uvicorn server:app --reload
```

Open `http://localhost:8000` in your browser.

---

## Project Structure

```
Catalouge_Generation_Tool/
├── server.py           # FastAPI app, routes, session management
├── gemini_service.py   # All Gemini API calls (analysis + image gen)
├── scraper.py          # Playwright scraper + manual upload fallback
├── config.py           # API keys, model names, directory config
├── requirements.txt    # Python dependencies
├── static/
│   ├── index.html      # Single-page app (5-step flow)
│   ├── style.css       # Dark premium design system
│   └── app.js          # Frontend state machine + SSE handling
├── uploads/            # Temp storage for uploaded images
└── outputs/            # Generated catalog images (per session)
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/scrape` | Scrape competitor URL |
| POST | `/api/upload-competitor` | Manual competitor image upload |
| POST | `/api/upload-product` | Upload your product images + description |
| POST | `/api/analyze` | Run analysis pipeline (returns intent + questions) |
| POST | `/api/generate-hero` | Generate the hero image |
| GET | `/api/generate-catalog/stream` | SSE stream — generates catalog images |
| POST | `/api/regenerate` | Regenerate a single catalog image |
| GET | `/api/download/{session_id}` | Download full catalog as ZIP |

---

## The 5-Step UI Flow

1. **Competitor Input** — Paste Amazon/Flipkart URL or upload images manually
2. **Your Product** — Upload product photos or enter a text description
3. **Analysis + Questions** — Review extracted intents, answer smart questions (or skip)
4. **Hero Image** — Generate and approve the visual anchor
5. **Catalog** — Watch images generate in real-time, download when done

---

## Brand

**Ruva** — Premium sanitaryware.
