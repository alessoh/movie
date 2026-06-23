"""End-to-end pipeline test in mock mode.

Runs the full orchestrator against the bundled sample novel with every
provider mocked, then asserts that a valid, non-empty MP4 with a real duration
is produced.  No API keys, no cost, runs in seconds.

Run with:  RUN_MODE=mock python -m pytest tests/ -s
       or:  RUN_MODE=mock python tests/test_pipeline_mock.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Force mock mode BEFORE importing config-dependent modules.
os.environ["RUN_MODE"] = "mock"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import ffmpeg_utils as ff  # noqa: E402
from pipeline.orchestrator import run_job  # noqa: E402
from pipeline.state import store  # noqa: E402


def test_pipeline_mock_produces_mp4():
    # Arrange: a session pointed at the sample novel.
    session = store.create()
    sample = ROOT / "tests" / "sample_novel.txt"
    work_dir = Path(session.work_dir)
    upload = work_dir / "upload.txt"
    shutil.copy(sample, upload)
    session.upload_path = str(upload)

    # Act: run the entire pipeline synchronously.
    run_job(session.token)

    # Assert: terminal success with a real movie file.
    s = store.get(session.token)
    assert s is not None, "session disappeared"
    assert s.status == "ready", f"job did not finish cleanly: status={s.status}, error={s.error}\n" + "\n".join(s.messages)
    assert s.movie_path, "no movie path recorded"

    movie = Path(s.movie_path)
    assert movie.exists(), "movie file was not created"
    assert movie.stat().st_size > 0, "movie file is empty"

    duration = ff.probe_duration(movie)
    assert duration > 1.0, f"movie has implausible duration: {duration}s"

    print(f"\nOK: produced {movie} ({movie.stat().st_size} bytes, {duration:.1f}s)")

    # Cleanup.
    shutil.rmtree(work_dir, ignore_errors=True)
    store.delete(session.token)


if __name__ == "__main__":
    test_pipeline_mock_produces_mp4()
    print("PASSED")
