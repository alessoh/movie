"""Step 4 - Condensation to a two-minute story.

Call the language model once to turn the full text into a title, a tight
logline, and a micro screenplay of 12-16 beats, each a single visible moment.
"""
from __future__ import annotations

import json

from config import settings
from pipeline.providers.base import LLMProvider

_SYSTEM = (
    "You are a film development editor who compresses entire novels into a "
    "two-minute movie. You keep the spine of the plot, the protagonist, and "
    "the emotional arc, and you ruthlessly drop subplots, side characters, "
    "and detail. You always answer with valid JSON only, no prose, no "
    "markdown fences."
)


def condense(llm: LLMProvider, story_text: str) -> dict:
    count = settings.shot_count
    prompt = f"""Compress the following novel into a micro screenplay of exactly {count} beats.

Each beat is a single moment the audience will SEE on screen, in chronological
order, that together tell the whole story arc from setup to resolution.

Return ONLY this JSON shape:
{{
  "title": "short evocative film title",
  "logline": "one-sentence logline capturing the whole film",
  "beats": [
    {{"index": 1, "moment": "one vivid sentence describing what we see"}}
  ]
}}

There must be exactly {count} beats. Novel text:
\"\"\"
{story_text}
\"\"\"
"""
    raw = llm.complete(_SYSTEM, prompt, max_tokens=4000)
    data = _parse_json(raw)
    if "beats" not in data or not isinstance(data["beats"], list) or not data["beats"]:
        raise RuntimeError("Condensation returned no beats.")
    data.setdefault("title", "Untitled")
    data.setdefault("logline", "")
    return data


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        # Strip code fences if the model added them despite instructions.
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    return json.loads(raw)
