"""Orchestrator.

Runs steps 3 through 10 in order as a single straight-through sequence,
emitting progress to the state store after each meaningful unit of work, and
owning the section-9 graceful-degradation contract.  The job always finishes
with a movie file or ends with a clear terminal error; it never waits for a
human.

Structured so a real queue (Celery/RQ) could later replace ``run_job``'s
threading without rewriting any step.
"""
from __future__ import annotations

import traceback
from pathlib import Path

from pipeline.providers import get_providers
from pipeline.state import store
from pipeline.steps import (
    step03_extract,
    step04_condense,
    step05_shotlist,
    step06_anchors,
    step07_clips,
    step08_narration,
    step09_music,
    step10_assemble,
)


def run_job(token: str) -> None:
    """Entry point for the background task.  Catches everything so a failure
    becomes a clean terminal error rather than a hung job."""
    session = store.get(token)
    if not session:
        return
    work_dir = Path(session.work_dir)
    try:
        _run(token, session.upload_path, work_dir)
    except _TerminalError as exc:
        store.fail(token, str(exc))
    except Exception as exc:  # noqa: BLE001 - last-resort safety net
        store.fail(token, f"Unexpected failure: {exc}")
        # Keep a trace in the message log for the operator.
        store.add_message(token, traceback.format_exc().splitlines()[-1])


class _TerminalError(Exception):
    """Raised when the job cannot continue and must stop with a clear error."""


def _run(token: str, upload_path: str, work_dir: Path) -> None:
    providers = get_providers()

    # --- Step 3: text extraction -----------------------------------------
    store.set_phase(token, "reading", "Reading your novel")
    try:
        story_text = step03_extract.extract_text(upload_path)
    except Exception as exc:
        raise _TerminalError(f"Could not read the uploaded file: {exc}")

    # --- Step 4: condensation --------------------------------------------
    store.set_phase(token, "shaping", "Shaping a two-minute story")
    try:
        beats = step04_condense.condense(providers.llm, story_text)
    except Exception as exc:
        # Language-model structure failed: stop before any paid video work.
        raise _TerminalError(f"Could not condense the story: {exc}")

    # --- Step 5: shot list -----------------------------------------------
    store.set_phase(token, "planning", "Planning the shots")
    try:
        shot_list = step05_shotlist.build_shot_list(providers.llm, beats)
    except Exception as exc:
        # Malformed plan after one repair attempt -> terminal, money unspent.
        raise _TerminalError(f"Could not build a valid shot list: {exc}")
    _save_json(work_dir / "shot_list.json", shot_list)
    store.add_message(token, f"Planned {len(shot_list['shots'])} shots: \"{shot_list.get('title','')}\"")

    # --- Step 6: anchors -------------------------------------------------
    store.set_phase(token, "designing", "Designing your characters")
    anchors = step06_anchors.build_anchors(
        providers.image, shot_list, work_dir,
        progress=lambda m: store.add_message(token, m),
    )

    # --- Step 7: clips (the real-video core) -----------------------------
    store.set_phase(token, "filming", "Filming the shots")

    def clip_progress(cur: int, total: int, msg: str) -> None:
        # Spread the filming phase across the 40..78 progress band.
        pct = 40 + int((cur / max(1, total)) * 38)
        store.add_message(token, msg, progress=pct)

    clip_results = step07_clips.generate_clips(
        providers.video, shot_list, anchors, work_dir, progress=clip_progress
    )
    degraded = sum(1 for r in clip_results if r.get("degraded"))
    dropped = sum(1 for r in clip_results if r.get("dropped"))
    if degraded:
        store.add_message(token, f"{degraded} shot(s) degraded to a held still.")
    if dropped:
        store.add_message(token, f"{dropped} shot(s) dropped after repeated failure.")

    # --- Step 8: narration -----------------------------------------------
    store.set_phase(token, "narrating", "Recording the narration")

    def narr_progress(cur: int, total: int, msg: str) -> None:
        pct = 78 + int((cur / max(1, total)) * 8)
        store.add_message(token, msg, progress=pct)

    step08_narration.generate_narration(
        providers.tts, clip_results, work_dir, progress=narr_progress
    )

    # --- Step 9: music ---------------------------------------------------
    store.set_phase(token, "scoring", "Scoring the music")
    total_duration = sum(
        float(r["shot"]["duration_seconds"])
        for r in clip_results
        if not r.get("dropped")
    )
    music_path = step09_music.generate_music(
        providers.music, shot_list, total_duration, work_dir
    )
    if music_path is None:
        store.add_message(token, "Music generation failed; the film will play without a score.")

    # --- Step 10: assembly -----------------------------------------------
    store.set_phase(token, "final_cut", "Final cut")
    out_path = work_dir / "movie.mp4"
    try:
        step10_assemble.assemble(clip_results, music_path, work_dir, out_path)
    except Exception as exc:
        raise _TerminalError(f"Final assembly failed: {exc}")

    store.finish(token, str(out_path))


def _save_json(path: Path, data: dict) -> None:
    import json

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
