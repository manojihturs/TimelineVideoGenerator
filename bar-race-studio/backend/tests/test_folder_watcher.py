from pathlib import Path

from app.services import folder_watcher


def _make_stable_file(tmp_path_factory, name="dataset.csv", content=b"a,b\n1,2\n"):
    unprocessed = tmp_path_factory
    path = unprocessed / name
    path.write_bytes(content)
    return path


def test_scan_claims_file_into_inprogress_before_processing(monkeypatch, tmp_path):
    unprocessed = tmp_path / "Unprocessed"
    inprogress = tmp_path / "InProgress"
    processed = tmp_path / "Processed"
    failed = tmp_path / "Failed"
    for d in (unprocessed, inprogress, processed, failed):
        d.mkdir()

    monkeypatch.setattr(folder_watcher, "UNPROCESSED_DIR", unprocessed)
    monkeypatch.setattr(folder_watcher, "INPROGRESS_DIR", inprogress)
    monkeypatch.setattr(folder_watcher, "PROCESSED_DIR", processed)
    monkeypatch.setattr(folder_watcher, "FAILED_DIR", failed)
    folder_watcher._last_seen_size.clear()

    seen_paths_during_processing: list[Path] = []

    def fake_process_file(path: Path) -> None:
        # the file must already be OUT of Unprocessed by the time
        # processing actually starts, so a concurrent/restarted scan
        # can't claim (and duplicate-render) it too
        assert not (unprocessed / path.name).exists()
        assert path.parent == inprogress
        seen_paths_during_processing.append(path)

    monkeypatch.setattr(folder_watcher, "_process_file", fake_process_file)

    src = unprocessed / "dataset.csv"
    src.write_bytes(b"a,b\n1,2\n")

    # first scan: sees the file, records its size, doesn't process yet
    # (the stability check needs two consecutive matching sizes)
    folder_watcher.scan_now()
    assert src.exists()
    assert seen_paths_during_processing == []

    # second scan: size unchanged since last poll -> claimed and processed
    folder_watcher.scan_now()
    assert not src.exists()
    assert len(seen_paths_during_processing) == 1
    assert (processed / "dataset.csv").exists()
    assert not list(inprogress.iterdir())


def test_interrupted_file_is_reclaimed_to_unprocessed_on_startup(monkeypatch, tmp_path):
    unprocessed = tmp_path / "Unprocessed"
    inprogress = tmp_path / "InProgress"
    for d in (unprocessed, inprogress):
        d.mkdir()

    monkeypatch.setattr(folder_watcher, "UNPROCESSED_DIR", unprocessed)
    monkeypatch.setattr(folder_watcher, "INPROGRESS_DIR", inprogress)

    # simulates a file left behind by a process that died mid-render
    orphaned = inprogress / "orphaned.csv"
    orphaned.write_bytes(b"a,b\n1,2\n")

    folder_watcher._reclaim_interrupted_files()

    assert not orphaned.exists()
    assert (unprocessed / "orphaned.csv").exists()
