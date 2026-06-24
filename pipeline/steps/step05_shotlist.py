"""Step 5 - Shot list with prompts.

Expand the beats into the validated shot-list JSON contract (section 6).  The
shot list is the single most important internal contract: every later step
reads it.  We validate against the schema and repair/regenerate once if it is
malformed.  If it still fails, we raise a terminal error BEFORE any paid video
work begins, so money is never spent on a broken plan.
"""
from __future__ import annotations

import json

from config import settings
from pipeline.providers.base import LLMProvider
from pipeline.steps.step04_condense import _parse_json

_SYSTEM = (
    "You are a director of photography turning story beats into a precise shot "
    "list for a two-minute narrated film. You answer with valid JSON only, no "
    "prose, no markdown fences."
)


def build_shot_list(llm: LLMProvider, beats: dict, cfg=None) -> dict:
    cfg = cfg or settings
    raw = llm.complete(_SYSTEM, _prompt(beats, cfg), max_tokens=6000)
    try:
        data = _parse_json(raw)
        validate_shot_list(data)
        return _normalize(data, cfg)
    except Exception:
        # One repair attempt with the error fed back in.
        repair_prompt = _prompt(beats, cfg) + (
            "\n\nYour previous answer was invalid. Return ONLY valid JSON that "
            "exactly matches the schema, with every required field present."
        )
        raw2 = llm.complete(_SYSTEM, repair_prompt, max_tokens=6000)
        data = _parse_json(raw2)  # may raise -> terminal error upstream
        validate_shot_list(data)
        return _normalize(data, cfg)


def _prompt(beats: dict, cfg) -> str:
    shot_len = cfg.shot_length_seconds
    guidance = (cfg.style_guidance or "").strip()
    guidance_line = (
        f"- Apply this overall visual style to the style_prompt and EVERY shot's "
        f"visual_prompt: {guidance}\n" if guidance else ""
    )
    return f"""Turn these story beats into a shot list. One shot per beat.

Beats:
{json.dumps(beats, indent=2)}

Return ONLY this JSON shape:
{{
  "title": "string",
  "logline": "string",
  "style_prompt": "global look, mood, palette, era applied to EVERY shot",
  "characters": [
    {{"id": "c1", "name": "string", "appearance_prompt": "stable physical description"}}
  ],
  "shots": [
    {{
      "index": 1,
      "duration_seconds": {shot_len},
      "visual_prompt": "what the camera sees in this shot",
      "narration": "one sentence the narrator speaks over this shot",
      "character_ids": ["c1"]
    }}
  ]
}}

Rules:
- One shot per beat, in order, index starting at 1.
- Each shot's duration_seconds should be {shot_len}.
- Every character_id referenced must exist in the characters array.
- Keep 1-4 named characters total; reuse the same ids across shots.
- narration is exactly one spoken sentence.
{guidance_line}"""


def validate_shot_list(data: dict) -> None:
    """Raise ValueError if ``data`` does not satisfy the shot-list contract."""
    if not isinstance(data, dict):
        raise ValueError("shot list is not an object")
    for key in ("title", "logline", "style_prompt", "characters", "shots"):
        if key not in data:
            raise ValueError(f"missing top-level key: {key}")
    if not isinstance(data["characters"], list):
        raise ValueError("characters must be a list")
    char_ids = set()
    for c in data["characters"]:
        if not isinstance(c, dict) or "id" not in c:
            raise ValueError("each character needs an id")
        char_ids.add(c["id"])
    shots = data["shots"]
    if not isinstance(shots, list) or not shots:
        raise ValueError("shots must be a non-empty list")
    for sh in shots:
        if not isinstance(sh, dict):
            raise ValueError("each shot must be an object")
        for key in ("index", "duration_seconds", "visual_prompt", "narration"):
            if key not in sh:
                raise ValueError(f"shot missing key: {key}")
        if not str(sh["visual_prompt"]).strip():
            raise ValueError("shot has empty visual_prompt")


def _normalize(data: dict, cfg=None) -> dict:
    """Coerce types, fill defaults, fix indices and character references."""
    cfg = cfg or settings
    char_ids = {c["id"] for c in data["characters"]}
    shot_len = cfg.shot_length_seconds
    # Reinforce the user's style guidance in the global style prompt so anchors
    # and clips both pick it up, even if the model under-applied it.
    guidance = (cfg.style_guidance or "").strip()
    if guidance:
        data["style_prompt"] = f"{data.get('style_prompt', '').strip()} | {guidance}".strip(" |")
    shots = data["shots"]
    for i, sh in enumerate(shots, start=1):
        sh["index"] = i
        try:
            sh["duration_seconds"] = int(sh.get("duration_seconds") or shot_len)
        except (TypeError, ValueError):
            sh["duration_seconds"] = shot_len
        if sh["duration_seconds"] <= 0:
            sh["duration_seconds"] = shot_len
        sh["narration"] = str(sh.get("narration", "")).strip()
        sh["visual_prompt"] = str(sh.get("visual_prompt", "")).strip()
        cids = sh.get("character_ids") or []
        sh["character_ids"] = [c for c in cids if c in char_ids]
    return data
