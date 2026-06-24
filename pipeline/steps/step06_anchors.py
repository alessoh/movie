"""Step 6 - Style and character anchors.

Generate a small set of reference images: one style frame from the style
prompt and one portrait per main character.  These anchor the look so the
film stays visually coherent across shots, and they double as the source for
the ``hold_still`` fallback in step 7.

Returns a dict mapping:
    {"style": Path, "characters": {char_id: Path}}
Anchor generation degrades gracefully: a failed anchor is simply omitted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from pipeline.providers.base import ImageProvider

ProgressFn = Callable[[str], None]


def build_anchors(
    image: ImageProvider,
    shot_list: dict,
    work_dir: Path,
    progress: Optional[ProgressFn] = None,
) -> Dict[str, object]:
    anchors_dir = work_dir / "anchors"
    anchors_dir.mkdir(parents=True, exist_ok=True)
    style_prompt = shot_list.get("style_prompt", "cinematic, filmic")

    result: Dict[str, object] = {"style": None, "characters": {}}

    # Style frame.
    style_path = anchors_dir / "style.png"
    try:
        if progress:
            progress("Designing the overall look")
        image.generate_image(
            f"Establishing style frame. {style_prompt}. Cinematic, no text, no watermark.",
            style_path,
        )
        result["style"] = style_path
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        if progress:
            progress(f"Style frame failed, continuing without it ({exc}).")

    # One portrait per character (cap to keep total images small).
    chars = shot_list.get("characters", [])[:4]
    char_map: Dict[str, Path] = {}
    for c in chars:
        cid = c.get("id")
        appearance = c.get("appearance_prompt", "")
        if not cid:
            continue
        portrait = anchors_dir / f"char_{cid}.png"
        try:
            if progress:
                progress(f"Designing {c.get('name', cid)}")
            image.generate_image(
                f"Character portrait. {appearance}. {style_prompt}. "
                f"Centered, cinematic, no text.",
                portrait,
            )
            char_map[cid] = portrait
        except Exception as exc:  # noqa: BLE001
            if progress:
                progress(f"Portrait for {cid} failed, continuing ({exc}).")
    result["characters"] = char_map
    return result


def anchor_for_shot(shot: dict, anchors: Dict[str, object]) -> Optional[Path]:
    """Pick the best image-to-video seed for a shot.

    The seed frame steers the whole clip, so it must match the framing: a
    character portrait makes a person-centric shot coherent, but seeding a wide
    establishing shot ("a spaceship over a planet") from a face makes the model
    try to morph that face into the scene. So establishing shots prefer the
    neutral style frame; character/action shots prefer a portrait and fall back
    to the style frame.
    """
    char_map: Dict[str, Path] = anchors.get("characters", {})  # type: ignore[assignment]
    style = anchors.get("style")
    style_path = style if isinstance(style, Path) else None

    portrait = _first_portrait(shot, char_map)
    if (shot.get("shot_type") or "").lower() == "establishing":
        return style_path or portrait
    return portrait or style_path


def _first_portrait(shot: dict, char_map: Dict[str, Path]) -> Optional[Path]:
    """First available character portrait for the characters in this shot."""
    for cid in shot.get("character_ids", []):
        if cid in char_map:
            return char_map[cid]
    return None
