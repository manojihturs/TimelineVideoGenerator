# Reelframe — local project → video pipeline

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.0-black.svg)](https://flask.palletsprojects.com/)
[![GitHub repo](https://img.shields.io/badge/github-manojihturs%2FTimelineVideoGenerator-181717?logo=github)](https://github.com/manojihturs/TimelineVideoGenerator)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A local web app: create a project, drop numbered images + a CSV of captions
into its folders, and generate a captioned video (desktop 16:9 up to 4K, or
mobile 9:16 up to 60s) with FFmpeg.

## Requirements

- Python 3.9+
- [FFmpeg](https://ffmpeg.org/download.html) installed and on your PATH
  (Windows: download a build, add its `bin` folder to PATH; test with
  `ffmpeg -version` in a terminal)

## Setup

```bash
cd video_project_app
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5050** in your browser.

## Using it

1. **New project** → enter a title → **Create**.
   This creates `projects/<title>/` with `Assets`, `Thumbnail`, `Data`,
   `Export`, `Narration` folders, and an empty `Data/data.csv`.
2. Drop your images into `Assets`, named **numerically**: `1.jpg`, `2.jpg`,
   `3.jpg`, etc. (`.jpg`/`.jpeg`/`.png` supported.)
3. Open `Data/data.csv` in Excel/Notepad and fill it in — **no header row**.
   Row 1 = fields for `1.jpg`, row 2 = fields for `2.jpg`, etc. Each row's
   columns become the stacked colored bands under that image — this is
   built as a "recap card" template (poster image + title/year/stat/verdict
   bands), but it works for **any topic**: just change what you put in each
   column.
   ```
   Baana Kaathadi,2010,10 Cr,FLOP
   Naalaiya Theerpu,1992,-,SUPERHIT
   ```
   Any number of columns works (2, 3, 5...) — each becomes its own band,
   evenly splitting the space below the image. Verdict-style words
   (FLOP, HIT, BLOCKBUSTER, AVERAGE, DISASTER, SUCCESS, SUPERHIT) are
   automatically colored (red/green/amber) — everything else renders in
   black with a white outline, matching the reference template.
4. Back in the app, refresh the project — the filmstrip and checklist turn
   teal once Assets and Data are both populated.
5. Choose **Desktop** (pick minutes/seconds + resolution up to 4K, 16:9) or
   **Mobile** (seconds only, max 60, fixed 9:16).
6. **Generate** — watch the progress bar, then download the mp4 from the
   Export list once it's done.

## Auto-fill from a category (optional)

Instead of manually collecting images and typing `data.csv` by hand, you can
define **categories** — reusable templates that say what CSV columns a
project needs (e.g. `Movie` → Name / Year of release / Box office status,
`Car` → Name / Year of release / Total sale count) — then either:

- **Fully automatic (Movie category only)**: type a topic (an actor's name)
  and the app pulls their entire filmography — title, year, poster image,
  and a computed box-office verdict — with zero manual data entry. See
  "Full auto-fetch" below.
- **Semi-automatic (any category)**: you supply the item list/data, the app
  fetches one matching image per item. See "Image-only fetch" below.

### Full auto-fetch (Movie category)

Uses **TMDb** (themoviedb.org), a free, official, structured movie
database API — not a search engine, so title/year/budget/revenue/poster
come back as real fields, not guessed from text. This is what makes
"topic in → finished project out" possible with no manual data entry.

1. Get a free API key at
   [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api).
2. Set it as an environment variable before running the app:
   ```bash
   export TMDB_API_KEY=your_key_here
   ```
3. In a project's **Content** panel, pick category **Movie**, type an
   actor's name into **Topic**, and click **Auto-fetch filmography**. Their
   dated movie credits are sorted by year, downloaded as posters into
   `Assets/1.jpg, 2.jpg, ...` (capped at 30 movies), and box-office verdict
   (Flop/Average/Hit/Blockbuster) is computed from each movie's
   budget-vs-revenue ratio — written straight into `Data/data.csv`.
   Review/edit the CSV afterward if you want to adjust anything.

API route: `POST /api/projects/<title>/auto-fetch` with
`{"category": "Movie", "topic": "Aamir Khan"}`.

### Image-only fetch (any category)

Images are sourced via the official **Google Custom Search JSON API**
(image search) — not scraping, so it respects Google's terms and won't get
blocked. You need your own key:

1. Get an API key at [console.cloud.google.com](https://console.cloud.google.com/)
   (enable the "Custom Search API").
2. Create a Programmable Search Engine at
   [programmablesearchengine.google.com](https://programmablesearchengine.google.com/)
   with **Image search** turned on, and note its Search Engine ID (`cx`).
3. Set both as environment variables before running the app:
   ```bash
   export GOOGLE_CSE_API_KEY=your_key_here
   export GOOGLE_CSE_CX=your_cx_here
   ```
   (Google's free tier is 100 queries/day; each item fetched uses one query.)

**Categories** — `GET/POST /api/categories`, `DELETE /api/categories/<name>`.
Ships with `Movie` and `Car` presets; add your own with any column list.

**Fetching content for a project** — `POST /api/projects/<title>/items`
with an ordered list, one entry per item, in the exact order you want
`1.jpg`, `2.jpg`, ... to end up in:
```json
{
  "category": "Movie",
  "items": [
    {"query": "Top Gun 1986", "row": ["Top Gun", "1986", "Blockbuster"]},
    {"query": "Days of Thunder 1990", "row": ["Days of Thunder", "1990", "Average"]}
  ]
}
```
You supply the row data (year, box-office status, sales count, etc.)
yourself — that figure doesn't come from a reliable structured API, so the
app doesn't try to guess it. It only automates the tedious part: finding
and downloading one matching image per item, in order, and writing the CSV
rows to line up with them. Re-fetching for a project replaces its existing
`Assets/` images and `Data/data.csv`.

## Thumbnail generation

In the project workspace, the **Thumbnail** panel lets you:
- pick which numbered asset image to use as the source
- choose Desktop (1280×720) or Mobile (1080×1920) aspect
- optionally set a custom headline (defaults to the project title)

Click **Generate thumbnail** and it builds a social-media-style cover image:
cropped to fill the frame (no letterboxing), contrast/saturation boosted,
a dark gradient scrim behind a bold stroked headline, an accent bar, and a
play-button cue so it reads as "video" at a glance. Saved to
`Thumbnail/thumbnail_<device>.jpg`. Re-generating overwrites the previous
one for that aspect.

## Narration / audio

Drop one or more audio files (`.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`) into
a project's `Narration` folder. On the next **Generate**:
- if multiple files are present, they're concatenated in filename order
  (so name them `1_intro.mp3`, `2_body.mp3`, etc. if order matters)
- the combined narration is looped if it's shorter than your chosen video
  duration, or trimmed if it's longer — either way the final video always
  runs exactly the duration you set
- if the Narration folder is empty, the video exports silent (this is
  optional, not required for Generate to be enabled)

### Background music (optional)

In a project's workspace, the **Background Music** panel pulls a track from
[Jamendo](https://www.jamendo.com/) — a royalty-free music catalog with a
real API — into `Music/`, which is mixed in automatically alongside
`Narration/` by the mixing behavior above (either folder, or both, feeds
the same pipeline). Needs a free Jamendo client ID:

1. Register at [devportal.jamendo.com](https://devportal.jamendo.com/) and
   create an app to get a Client ID.
2. Set it as an environment variable:
   ```bash
   export JAMENDO_CLIENT_ID=your_client_id_here
   ```
3. Optionally type a mood/genre (e.g. "cinematic", "upbeat") and click
   **Add background music** — leave it blank for a popular pick. Or click
   **Indian style** for music in an Indian genre (sitar/carnatic/bhangra/
   general "indian" tags) — independent artists' work, not actual film
   songs. Real trending Bollywood/Tamil/Telugu/Malayalam songs are
   copyrighted commercial recordings and this app won't source them.

**Every Jamendo track requires attribution** (all of them are licensed
Creative Commons "Attribution", at minimum) — there's no such thing as
truly attribution-free royalty-free music here. The app only picks tracks
cleared for commercial use with no ShareAlike/NoDerivatives restrictions,
and writes the required credit line to `Music/ATTRIBUTION.txt` — credit
the artist if you publish the video.

## How generation works

- One "card" is built per **CSV row that has a matching numbered image** —
  the CSV is the source of truth for what gets built, not the image count.
- Each card: source image is cropped to best-fill a colored panel up top
  (no letterboxing/empty margin), with one colored band per non-empty
  column stacked below it. Band count — and therefore the whole card's
  layout — automatically adapts to however many columns that row has.
- The poster background carries a faint diagonal-stripe texture baked in;
  it's static in the image itself, but since the whole thing scrolls, it
  animates for free.
- All cards are laid out left-to-right with a fixed, equal gap — never
  overlapping — into one wide strip image.
- The final video is a single continuous **right-to-left scroll** across
  that strip at constant speed, timed so it runs exactly your chosen
  duration: no cuts between cards, the scroll itself is the transition.

## Notes on this build

- Single-user, local-only — no auth, no database. Project state is just the
  folders on disk; render jobs live in memory while the app is running.
- If you restart the app mid-render, that job is lost — just click Generate
  again once it's back up.
- Windows paths / long filenames: keep project titles reasonably short and
  avoid special characters — the app already strips anything unsafe.
