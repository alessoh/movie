"""Step 10 - Assembly and final mux.

Concatenate the shot clips in order, place each narration line under its shot,
lay the music underneath at a lower level ducked beneath speech, add short
crossfades between shots, normalize loudness, and export one self-contained
H.264/AAC MP4.  Fully automatic; verifies a nonzero-duration output.

Implemented as three robust stages:
  1. Per-shot segments: normalize each clip to a common format and mix its
     narration over the clip's audio.
  2. Concatenate segments with brief audio+video crossfades.
  3. Mix the ducked music bed under the narration and loudness-normalize.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pipeline import ffmpeg_utils as ff
from pipeline.ffmpeg_utils import X264_PRESET

CROSSFADE = 0.5  # seconds at each shot boundary
NARRATION_GAIN = 1.6
MUSIC_GAIN = 0.28


def assemble(
    clip_results: List[dict],
    music_path: Optional[Path],
    work_dir: Path,
    out_path: Path,
) -> Path:
    seg_dir = work_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    active = [r for r in clip_results if r.get("clip") and not r.get("dropped") and Path(r["clip"]).exists()]
    if not active:
        raise RuntimeError("No usable clips were produced; cannot assemble a movie.")

    # --- Stage 1: per-shot segments ---------------------------------------
    segments: List[Path] = []
    durations: List[float] = []
    for r in active:
        clip = Path(r["clip"])
        narration = r.get("narration_audio")
        seg = seg_dir / f"seg_{r['index']:02d}.mp4"
        dur = _build_segment(clip, narration, r["shot"], seg)
        segments.append(seg)
        durations.append(dur)

    # --- Stage 2: concatenate with crossfades -----------------------------
    concat_path = work_dir / "concat.mp4"
    if len(segments) == 1:
        # Nothing to crossfade.
        ff.run_ffmpeg(["-i", str(segments[0]), "-c", "copy", str(concat_path)])
    else:
        _concat_with_crossfades(segments, durations, concat_path)

    # --- Stage 3: music bed + loudness normalization ----------------------
    _mix_music_and_normalize(concat_path, music_path, out_path)

    # --- Verify -----------------------------------------------------------
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError("Final mux produced no output file.")
    if ff.probe_duration(out_path) <= 0.1:
        raise RuntimeError("Final movie has zero duration.")
    return out_path


# --------------------------------------------------------------------------- #
def _build_segment(clip: Path, narration: Optional[Path], shot: dict, out: Path) -> float:
    """Normalize one clip to canonical format and mix narration over its audio.

    Returns the segment duration in seconds.
    """
    dur = ff.probe_duration(clip)
    if dur <= 0.1:
        dur = float(shot.get("duration_seconds", 8))

    clip_has_audio = ff.has_audio(clip)

    inputs: List[str] = ["-i", str(clip)]
    next_idx = 1
    narr_idx = None
    if narration is not None and Path(narration).exists():
        inputs += ["-i", str(narration)]
        narr_idx = next_idx
        next_idx += 1
    # Guaranteed silent bed so there is always an audio stream to map.
    inputs += ["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={ff.SAMPLE_RATE}"]
    silence_idx = next_idx

    vfilter = (
        f"[0:v]scale={ff.WIDTH}:{ff.HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={ff.WIDTH}:{ff.HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={ff.FPS},format=yuv420p[v]"
    )

    # Build the audio mix: silence bed + clip audio (if any) + narration (boosted).
    amix_labels = [f"[{silence_idx}:a]"]
    pre_filters = []
    if clip_has_audio:
        amix_labels.insert(0, "[0:a]")
    if narr_idx is not None:
        pre_filters.append(f"[{narr_idx}:a]volume={NARRATION_GAIN},apad[narr]")
        amix_labels.append("[narr]")

    afilter_parts = list(pre_filters)
    afilter_parts.append(
        f"{''.join(amix_labels)}amix=inputs={len(amix_labels)}:duration=first:"
        f"dropout_transition=0,aresample={ff.SAMPLE_RATE}[a]"
    )

    filter_complex = vfilter + ";" + ";".join(afilter_parts)

    ff.run_ffmpeg(
        [
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "[a]",
            "-t", f"{dur:.2f}",
            "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", str(ff.SAMPLE_RATE), "-ac", "2",
            str(out),
        ]
    )
    return ff.probe_duration(out) or dur


def _concat_with_crossfades(segments: List[Path], durations: List[float], out: Path) -> None:
    """Chain xfade (video) and acrossfade (audio) across all segments."""
    # Clamp crossfade so it never exceeds the shortest clip.
    t = min(CROSSFADE, min(durations) / 2 - 0.05)
    t = max(0.1, t)

    inputs: List[str] = []
    for seg in segments:
        inputs += ["-i", str(seg)]

    vparts: List[str] = []
    aparts: List[str] = []
    v_prev = "[0:v]"
    a_prev = "[0:a]"
    cum = durations[0]
    for i in range(1, len(segments)):
        offset = cum - t
        v_out = f"[v{i}]"
        a_out = f"[a{i}]"
        vparts.append(
            f"{v_prev}[{i}:v]xfade=transition=fade:duration={t:.2f}:offset={offset:.2f}{v_out}"
        )
        aparts.append(f"{a_prev}[{i}:a]acrossfade=d={t:.2f}{a_out}")
        v_prev = v_out
        a_prev = a_out
        cum = cum + durations[i] - t

    filter_complex = ";".join(vparts + aparts)
    ff.run_ffmpeg(
        [
            *inputs,
            "-filter_complex", filter_complex,
            "-map", v_prev, "-map", a_prev,
            "-c:v", "libx264", "-preset", X264_PRESET, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", str(ff.SAMPLE_RATE), "-ac", "2",
            str(out),
        ]
    )


def _mix_music_and_normalize(concat_path: Path, music_path: Optional[Path], out: Path) -> None:
    """Lay ducked music under the narration track and loudness-normalize."""
    loudnorm = "loudnorm=I=-16:TP=-1.5:LRA=11"

    if music_path is None or not Path(music_path).exists():
        # No music: just normalize loudness.
        ff.run_ffmpeg(
            [
                "-i", str(concat_path),
                "-filter_complex", f"[0:a]{loudnorm}[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-ar", str(ff.SAMPLE_RATE),
                "-movflags", "+faststart",
                str(out),
            ]
        )
        return

    # Duck the music beneath speech via sidechain compression keyed on narration.
    filter_complex = (
        f"[0:a]asplit=2[na][key];"
        f"[1:a]volume={MUSIC_GAIN},aresample={ff.SAMPLE_RATE}[mus];"
        f"[mus][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=300[musd];"
        f"[na][musd]amix=inputs=2:duration=first:dropout_transition=0,{loudnorm}[a]"
    )
    ff.run_ffmpeg(
        [
            "-i", str(concat_path),
            "-i", str(music_path),
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-ar", str(ff.SAMPLE_RATE),
            "-movflags", "+faststart",
            "-shortest",
            str(out),
        ]
    )
