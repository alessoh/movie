# novel-to-movie

Upload a novel, get a **two-minute movie** made of generated video clips, with a
single narrator voice over a music bed. Free to the visitor, no login. The
operator funds and supplies all API keys, which live only on the server.

The defining design choice is **aggressive condensation**: a whole novel is
compressed to ~15 story beats and told through a narrator speaking over the
visuals. This deliberately avoids per-character voice casting and lip-sync — the
hardest, most expensive parts of filmmaking — while still producing genuine
video rather than a slideshow.

---

## How it works

A single straight-through pipeline runs automatically once a visitor uploads a
file and presses start:

| Step | Stage | What happens |
|------|-------|--------------|
| 3 | Text extraction | Read .txt / .docx / .pdf into clean plain text |
| 4 | Condensation | LLM → title, logline, 12–16 story beats |
| 5 | Shot list | LLM → validated shot-list JSON (the core contract) |
| 6 | Anchors | One style frame + one portrait per character |
| 7 | Clips | One image-to-video clip per shot (the real-video core) |
| 8 | Narration | One narrator line per shot (single voice) |
| 9 | Music | One background score for the whole film |
| 10 | Assembly | FFmpeg concat + crossfades + ducked music + loudnorm → MP4 |

Steps 11–12 (progress reporting and delivery/cleanup) wrap the run.

Every stage **degrades gracefully** so the job always ends with a finished
movie or a clear terminal error, and never waits for a human (see
[Graceful degradation](#graceful-degradation)).

---

## Quick start

### 1. Install

```bash
# System dependency: FFmpeg must be on PATH.
#   macOS:   brew install ffmpeg
#   Ubuntu:  sudo apt-get install -y ffmpeg

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Run the free mock test first (no keys, no cost)

Mock mode replaces every provider with a local generator that produces real but
trivial media, so the whole pipeline + assembly + UI run end to end in seconds:

```bash
RUN_MODE=mock python -m pytest tests/ -s
```

This asserts a valid, non-empty MP4 with a real duration is produced.

### 3. Start the service — the single command

```bash
RUN_MODE=mock python main.py
```

Open <http://localhost:8000>, upload `tests/sample_novel.txt`, press
**Make my movie**, and watch live progress through to an inline player and a
download button. (Drop the `RUN_MODE=mock` prefix once your real keys are set in
`.env` — `RUN_MODE` defaults to `real` there.)

---

## Mock vs. real mode

- **`RUN_MODE=mock`** — all providers are mocked. No keys required, no API
  calls, no cost. Use it to exercise orchestration, progress, assembly, and the
  UI. The included test runs in this mode.
- **`RUN_MODE=real`** — uses the configured providers. Required keys are checked
  at startup and the server **fails fast** with a readable error if any are
  missing.

Only switch to real mode after the mock test passes.

---

## Environment variables

All configuration lives in `.env` (copy from `.env.example`). Keys are read
**only** through `config.py` and are never sent to the browser.

| Variable | Meaning |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude key for the LLM passes |
| `AGGREGATOR_API_KEY` | Key for the image/video/music aggregator (fal.ai or Replicate) |
| `ELEVENLABS_API_KEY` | ElevenLabs key for narration |
| `LLM_PROVIDER` / `IMAGE_PROVIDER` / `VIDEO_PROVIDER` / `TTS_PROVIDER` / `MUSIC_PROVIDER` | Adapter selection |
| `AGGREGATOR` | `fal` (default) or `replicate` |
| `LLM_MODEL` / `IMAGE_MODEL` / `VIDEO_MODEL` / `MUSIC_MODEL` / `TTS_VOICE_ID` | Model identifiers (configurable, not hardcoded) |
| `TARGET_DURATION_SECONDS` / `SHOT_COUNT` / `SHOT_LENGTH_SECONDS` | Movie shape |
| `MAX_RETRIES_PER_SHOT` | Retries per provider call before fallback |
| `MAX_MOVIES_PER_SESSION` | Per-session quota (default 1) |
| `FAILED_SHOT_FALLBACK` | `hold_still` (default) or `drop_shot` |
| `SESSION_TTL_MINUTES` | How long session files live before the sweep deletes them |
| `MAX_UPLOAD_MB` | Upload size cap |
| `RUN_MODE` | `real` or `mock` |
| `PORT` / `HOST` | Where the server listens |

---

## Graceful degradation

The job always reaches a finished movie or a clear terminal error:

- Every provider call retries a bounded number of times with short backoff.
- A **shot** that still fails → `hold_still` substitutes a held still from its
  anchor image (preserving narration alignment), or `drop_shot` removes the shot.
- A **narration** line that fails → that shot plays with no narration.
- The **music** track that fails → the film plays with no score.
- A **malformed LLM plan** → one repair attempt; if it still fails, the job
  stops with a terminal error **before any paid video work**, so money is never
  spent on a broken plan.

Every degradation is recorded in the session message log.

---

## Security & cost guardrails

- No login, no account — each visit is an anonymous random token.
- API keys are server-side environment variables only; they never appear in
  client code or responses.
- A per-session quota caps each visit to one movie and bounds retries, so a
  public free page cannot run up an unbounded bill.
- Session working folders (uploads + intermediate assets) are deleted on a timer
  (`SESSION_TTL_MINUTES`), since there is no account to keep them in.

---

## Project layout

```
novel-to-movie/
  main.py                 FastAPI app: routes, SSE progress, static, delivery, cleanup
  config.py               Single ingress for all keys + tunables
  pipeline/
    orchestrator.py       Runs steps 3–10, emits progress, owns fallbacks
    state.py              In-memory session store (+ optional SQLite mirror)
    ffmpeg_utils.py       FFmpeg/FFprobe wrappers
    steps/                step03_extract … step10_assemble
    providers/            base interfaces + anthropic / aggregator / elevenlabs / mock
  web/                    index.html, style.css, app.js (single light-mode page)
  storage/sessions/       per-session working folders (gitignored)
  tests/                  sample_novel.txt + end-to-end mock test
```

---

## Operator: verify before going live

The real provider adapters are written against each service's documented
interface, but the exact model ids and a few request/response field names shift
over time. Each real adapter carries an `OPERATOR VERIFY` note describing what to
confirm against current docs:

- `providers/llm_anthropic.py` — endpoint, `anthropic-version`, `LLM_MODEL`.
- `providers/_aggregator_client.py` — base URLs, auth header, result field names
  for your chosen fal.ai / Replicate models.
- `providers/images_aggregator.py`, `video_aggregator.py`, `music_aggregator.py`
  — each model's input schema (e.g. duration units, `image_url` for i2v).
- `providers/tts_elevenlabs.py` — **replace `TTS_VOICE_ID`** with a real voice id
  and confirm the TTS `model_id`.

Until those are confirmed, the entire system remains fully exercisable through
mock mode.
