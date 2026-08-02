"""Watches storage/uploads/Unprocessed for new files (dropped there
directly, or written by the /api/format endpoint) and, for each one,
auto-detects its columns, renders a 5-minute desktop video and a 60-second
mobile short, then moves the source file to Processed (or Failed, with an
error note alongside it, if anything along the way didn't work) so it's
never picked up and re-processed on the next poll.

A file is claimed into InProgress the instant a scan picks it up, before
rendering even starts — a render can run for 10-20+ minutes, and without
this, killing/restarting the process mid-render leaves the file sitting
untouched in Unprocessed, where the next scan (this run or a future one)
sees it as brand new and renders a duplicate pair of videos from scratch."""
import re
import shutil
import threading
import time
from pathlib import Path

from app.core.settings import FAILED_DIR, FOLDER_WATCH_INTERVAL_S, INPROGRESS_DIR, PROCESSED_DIR, UNPROCESSED_DIR
from app.models.config import ColumnMapping, RaceConfig, Resolution, SocialPreset
from app.services import job_manager
from app.services.column_detector import detect_columns
from app.services.dataset_service import load_dataframe
from app.services.timeline_parser import match_header

JOB_TIMEOUT_S = 3600
JOB_POLL_INTERVAL_S = 3


def _humanize_title(path: Path) -> str:
    return re.sub(r"[_\-]+", " ", path.stem).strip().title()


def _duration_config(mapping: ColumnMapping, target_seconds: float, fps: int) -> int:
    """Same math used throughout this session's manual renders: pick a
    steps_per_transition so the finished video's total frame count lands
    on the target duration, given however many periods this dataset has."""
    periods = len(mapping.value_columns)
    transitions = max(1, periods - 1)
    target_frames = target_seconds * fps
    steps = max(1, round((target_frames - periods) / transitions))
    return round(steps / fps * 1000)


def _year_span(mapping: ColumnMapping) -> int | None:
    """Years covered by the dataset's timeline columns (max - min + 1),
    however the timeline is actually broken down (months/quarters/weeks
    all still carry a year component) — None if no column carries a
    recognizable year at all (e.g. a purely quarter-only or week-only
    timeline with no year prefix)."""
    years = [m.sort_key[0] for col in mapping.value_columns if (m := match_header(col)) and m.sort_key and m.sort_key[0]]
    return (max(years) - min(years) + 1) if years else None


def _desktop_target_seconds(mapping: ColumnMapping) -> float:
    """Longer historical spans get a longer desktop video so there's
    still time to read each period before the race moves on, rather than
    cramming e.g. 200 years of monthly data into the same fixed 5
    minutes a 10-year dataset gets."""
    span = _year_span(mapping)
    if span is None or span < 100:
        return 300  # 5 min
    if span < 150:
        return 480  # 8 min
    if span < 200:
        return 660  # 11 min
    return 780  # 13 min


def _build_configs(mapping: ColumnMapping, title: str, source_label: str) -> tuple[RaceConfig, RaceConfig]:
    fps = 30
    common = dict(
        mapping=mapping, title=title, data_source_label=source_label,
        fps=fps, bar_count=15, orientation="horizontal", show_images=True,
        overlay_labels_on_bars=True, image_position="outside_left", show_clock_icon=True,
    )
    desktop = RaceConfig(
        dataset_id="watcher", resolution=Resolution.HD_1080P,
        transition_duration_ms=_duration_config(mapping, _desktop_target_seconds(mapping), fps), **common,
    )
    mobile = RaceConfig(
        dataset_id="watcher", resolution=Resolution.VERTICAL_1080X1920,
        social_preset=SocialPreset.YOUTUBE_SHORTS,
        transition_duration_ms=_duration_config(mapping, 60, fps), **common,
    )
    return desktop, mobile


def _wait_for_job(job_id: str) -> dict:
    deadline = time.time() + JOB_TIMEOUT_S
    while time.time() < deadline:
        job = job_manager.JOBS.get(job_id)
        if job and job["status"] in ("done", "failed"):
            return job
        time.sleep(JOB_POLL_INTERVAL_S)
    raise TimeoutError(f"Render job {job_id} did not finish within {JOB_TIMEOUT_S}s")


def _process_file(path: Path) -> None:
    df = load_dataframe(path)
    detected = detect_columns(df)
    if not detected.entity_column or not detected.value_columns:
        raise ValueError("Could not auto-detect an entity column and timeline columns in this file.")

    mapping = ColumnMapping(
        entity_column=detected.entity_column,
        category_column=detected.category_column,
        image_column=detected.image_column,
        timeline_start_column=detected.value_columns[0],
        timeline_end_column=detected.value_columns[-1],
        value_columns=detected.value_columns,
    )
    title = _humanize_title(path)
    desktop_config, mobile_config = _build_configs(mapping, title, f"Auto-processed from {path.name}")

    desktop_job_id = job_manager.start_render_job(desktop_config, str(path))
    mobile_job_id = job_manager.start_render_job(mobile_config, str(path))

    desktop_job = _wait_for_job(desktop_job_id)
    mobile_job = _wait_for_job(mobile_job_id)

    if desktop_job["status"] != "done" or mobile_job["status"] != "done":
        errors = [j["error"] for j in (desktop_job, mobile_job) if j.get("error")]
        raise RuntimeError("; ".join(errors) or "Render job failed")


def _move_with_note(src: Path, dest_dir: Path, note: str | None = None) -> Path:
    dest = dest_dir / src.name
    counter = 2
    while dest.exists():
        dest = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1
    shutil.move(str(src), str(dest))
    if note:
        dest.with_suffix(dest.suffix + ".error.txt").write_text(note, encoding="utf-8")
    return dest


_last_seen_size: dict[str, int] = {}


def _reclaim_interrupted_files() -> None:
    """Runs once at startup. Anything sitting in InProgress means the
    previous process died mid-render (a clean run always empties this
    directory via _move_with_note in scan_now) — move it back to
    Unprocessed so it's retried exactly once, rather than staying stuck
    forever or a naive "just rescan Unprocessed" approach silently
    re-rendering it every single restart."""
    for entry in list(INPROGRESS_DIR.iterdir()):
        if entry.is_file():
            _move_with_note(entry, UNPROCESSED_DIR)


def scan_now() -> None:
    """Runs one scan pass immediately — used both by the background poll
    loop below and by POST /api/format/run-now, so the "Auto-Generate"
    button doesn't have to wait for the next scheduled tick."""
    seen_this_scan: set[str] = set()
    for entry in sorted(UNPROCESSED_DIR.iterdir()):
        if not entry.is_file() or entry.name.startswith("_incoming") or entry.name.startswith("."):
            continue
        key = str(entry)
        seen_this_scan.add(key)
        size = entry.stat().st_size
        # A file dropped in directly (not via /api/format, which writes
        # atomically) may still be mid-copy — only process once its size
        # has held steady across two consecutive polls.
        if _last_seen_size.get(key) != size:
            _last_seen_size[key] = size
            continue
        _last_seen_size.pop(key, None)

        # Claimed into InProgress before any rendering starts — see
        # module docstring for why this specific ordering matters.
        claimed = _move_with_note(entry, INPROGRESS_DIR)
        try:
            _process_file(claimed)
            _move_with_note(claimed, PROCESSED_DIR)
        except Exception as e:
            _move_with_note(claimed, FAILED_DIR, note=str(e))

    for key in list(_last_seen_size):
        if key not in seen_this_scan:
            _last_seen_size.pop(key, None)


def _watch_loop() -> None:
    while True:
        try:
            scan_now()
        except Exception:
            pass  # a scan-level failure shouldn't kill the watcher thread
        time.sleep(FOLDER_WATCH_INTERVAL_S)


def start_watcher() -> None:
    _reclaim_interrupted_files()
    threading.Thread(target=_watch_loop, daemon=True).start()
