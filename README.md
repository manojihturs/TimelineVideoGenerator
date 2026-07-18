# Reelframe — local project → video pipeline

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.0-black.svg)](https://flask.palletsprojects.com/)
[![GitHub repo](https://img.shields.io/badge/github-manojihturs%2FTimelineVideoGenerator-181717?logo=github)](https://github.com/manojihturs/TimelineVideoGenerator)

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
