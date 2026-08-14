"""Fully automatic pipeline: fetch real stock market data (yfinance, no
API key needed), build a "Most Valuable Companies" bar-chart-race CSV,
submit it to the already-running bar-race-studio backend for both
desktop and mobile renders, and mix in a synthesized narration track
describing the final standings — no manual data entry or interpretation
at any step.

Usage:
    python scripts/auto_finance_video.py

Requires:
    - bar-race-studio's FastAPI backend running on http://127.0.0.1:8000
      (python -m uvicorn app.main:app --port 8000, from bar-race-studio/backend)
    - pip install yfinance pyttsx3
"""
import csv
import glob
import io
import os
import shutil
import subprocess
import sys
import time

import requests
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_ffmpeg():
    """Prefer the winget-installed full ffmpeg build over shutil.which()'s
    first PATH hit — some machines have an older/partial ffmpeg earlier on
    PATH (e.g. bundled by an unrelated Python package) that's missing
    filters this project depends on (like xfade, added in FFmpeg 4.3), so
    check the known-good winget install first."""
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        pattern = os.path.join(
            local_appdata, "Microsoft", "WinGet", "Packages",
            "Gyan.FFmpeg_*", "ffmpeg-*-full_build", "bin", "ffmpeg.exe",
        )
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"


FFMPEG_BIN = resolve_ffmpeg()
BAR_RACE_API = "http://127.0.0.1:8000"
OUTPUT_DIR = os.path.join(BASE_DIR, "Finance Videos")

# Curated mega-cap watchlist — a fixed, well-known set makes for a
# coherent "who's #1" story (e.g. Nvidia's rise) rather than a noisy,
# unpredictable list from a daily top-movers feed.
TICKERS = {
    "AAPL": ("Apple", "apple.com"),
    "MSFT": ("Microsoft", "microsoft.com"),
    "GOOGL": ("Alphabet", "abc.xyz"),
    "AMZN": ("Amazon", "amazon.com"),
    "NVDA": ("Nvidia", "nvidia.com"),
    "META": ("Meta", "meta.com"),
    "TSLA": ("Tesla", "tesla.com"),
    "BRK-B": ("Berkshire Hathaway", "berkshirehathaway.com"),
    "TSM": ("TSMC", "tsmc.com"),
    "AVGO": ("Broadcom", "broadcom.com"),
    "LLY": ("Eli Lilly", "lilly.com"),
    "V": ("Visa", "visa.com"),
    "JPM": ("JPMorgan Chase", "jpmorganchase.com"),
    "WMT": ("Walmart", "walmart.com"),
    "ORCL": ("Oracle", "oracle.com"),
}
HISTORY_PERIOD = "4y"
HISTORY_INTERVAL = "1mo"


def fetch_market_cap_series():
    """Approximate historical market cap per ticker as
    (current shares outstanding) x (historical monthly close) — the
    standard approximation these "market cap race" videos use, since
    real historical shares-outstanding series aren't freely available.
    Returns {ticker: {period_label: market_cap}}."""
    series = {}
    for ticker in TICKERS:
        t = yf.Ticker(ticker)
        shares = t.get_info().get("sharesOutstanding")
        if not shares:
            continue
        hist = t.history(period=HISTORY_PERIOD, interval=HISTORY_INTERVAL)
        if hist.empty:
            continue
        by_period = {}
        for date, row in hist.iterrows():
            label = date.strftime("%Y-%m")
            by_period[label] = row["Close"] * shares
        series[ticker] = by_period
        time.sleep(0.3)  # be polite to the unofficial endpoint
    return series


def build_csv(series):
    """Company, Image URL, then one column per month — the shape
    bar-race-studio's column detector recognizes as entity/image/timeline
    without needing manual column mapping."""
    all_periods = sorted({p for by_period in series.values() for p in by_period})
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Company", "Image URL", *all_periods])
    for ticker, (name, domain) in TICKERS.items():
        if ticker not in series:
            continue
        row = [name, f"https://logo.clearbit.com/{domain}"]
        row += [series[ticker].get(p, "") for p in all_periods]
        writer.writerow(row)
    return buf.getvalue(), all_periods


def upload_dataset(csv_text):
    files = {"file": ("most_valuable_companies.csv", csv_text.encode("utf-8"), "text/csv")}
    res = requests.post(f"{BAR_RACE_API}/api/uploads", files=files, timeout=30)
    res.raise_for_status()
    return res.json()["dataset_id"]


def render(dataset_id, periods, device):
    value_columns = periods
    mapping = {
        "entity_column": "Company",
        "category_column": None,
        "image_column": "Image URL",
        "timeline_start_column": value_columns[0],
        "timeline_end_column": value_columns[-1],
        "value_columns": value_columns,
    }
    common = dict(
        dataset_id=dataset_id, mapping=mapping,
        title="Most Valuable Companies in the World",
        data_source_label="Yahoo Finance (approximate market cap)",
        fps=30, bar_count=12, orientation="horizontal",
        show_images=True, overlay_labels_on_bars=True,
        image_position="outside_left", show_clock_icon=True,
    )
    if device == "desktop":
        payload = {**common, "resolution": "1080p", "transition_duration_ms": 900}
        total_seconds = 60
    else:
        payload = {
            **common, "resolution": "vertical_1080x1920", "social_preset": "youtube_shorts",
            "transition_duration_ms": 700,
        }
        total_seconds = 30

    res = requests.post(f"{BAR_RACE_API}/api/renders", json=payload, timeout=30)
    res.raise_for_status()
    job_id = res.json()["job_id"]

    deadline = time.time() + 900
    while time.time() < deadline:
        job = requests.get(f"{BAR_RACE_API}/api/renders/{job_id}", timeout=15).json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(3)
    if job["status"] != "done":
        raise RuntimeError(f"{device} render failed: {job.get('error')}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"most_valuable_companies_{device}.mp4")
    video = requests.get(f"{BAR_RACE_API}/api/renders/{job_id}/download", timeout=60)
    with open(out_path, "wb") as f:
        f.write(video.content)
    return out_path


def build_narration_text(series, periods):
    """Final-period standings, top 5, read out as the video's narration —
    generated purely from the fetched data, no manual scripting."""
    latest = periods[-1]
    ranked = sorted(
        ((TICKERS[t][0], vals.get(latest)) for t, vals in series.items() if vals.get(latest)),
        key=lambda x: x[1], reverse=True,
    )[:5]
    lines = ["The world's most valuable companies, ranked by market capitalization."]
    for i, (name, cap) in enumerate(ranked, start=1):
        lines.append(f"Number {i}: {name}, at {cap / 1e12:.1f} trillion dollars.")
    lines.append("Thanks for watching. Please like, subscribe, and comment your predictions for next year.")
    return lines


def mux_narration(video_path, narration_lines, out_path):
    """Synthesizes narration_lines with one persistent TTS engine (see
    app.py's synthesize_narration_batch for why that matters over
    re-initializing per line) and mixes it under the video's existing
    background music."""
    import pyttsx3

    tmp_dir = os.path.join(OUTPUT_DIR, "_narration_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    engine = pyttsx3.init()
    for voice in engine.getProperty("voices"):
        if "zira" in voice.name.lower():
            engine.setProperty("voice", voice.id)
            break
    engine.setProperty("rate", 175)
    wav_paths = []
    for i, line in enumerate(narration_lines):
        wav_path = os.path.join(tmp_dir, f"{i:03d}.wav")
        engine.save_to_file(line, wav_path)
        wav_paths.append(wav_path)
    engine.runAndWait()
    wav_paths = [p for p in wav_paths if os.path.isfile(p) and os.path.getsize(p) > 0]
    if not wav_paths:
        return video_path  # narration failed; ship the video with just its music

    concat_list = os.path.join(tmp_dir, "concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in wav_paths:
            f.write(f"file '{p}'\n")
    narration_wav = os.path.join(tmp_dir, "narration.wav")
    subprocess.run(
        [FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", concat_list, narration_wav],
        check=True, capture_output=True,
    )

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_path,
        "-i", narration_wav,
        "-filter_complex",
        "[0:a]volume=0.25[bg];[1:a]volume=1.6[voice];[bg][voice]amix=inputs=2:duration=first[aout]",
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


if __name__ == "__main__":
    print("Fetching market data...")
    series = fetch_market_cap_series()
    if not series:
        print("No data fetched — aborting.")
        sys.exit(1)

    csv_text, periods = build_csv(series)
    print(f"Fetched {len(series)} companies across {len(periods)} months.")

    print("Uploading dataset...")
    dataset_id = upload_dataset(csv_text)

    narration_lines = build_narration_text(series, periods)

    for device in ("desktop", "mobile"):
        print(f"Rendering {device}...")
        video_path = render(dataset_id, periods, device)
        print(f"Adding narration to {device}...")
        final_path = video_path.replace(".mp4", "_narrated.mp4")
        mux_narration(video_path, narration_lines, final_path)
        print(f"[done] {device} -> {final_path}")
