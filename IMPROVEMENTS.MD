# IMPROVEMENTS PLAN - Penman

Backlog techniczny z estymacjami: `BACKLOG.MD`.

## Status Update (2026-02-19)
- Completed (P0): PEN-001, PEN-002, PEN-003, PEN-004, PEN-005, PEN-006, PEN-023, PEN-024.
- Completed (P1): PEN-007, PEN-008, PEN-009, PEN-010, PEN-011.
- Completed (P2): PEN-012, PEN-013, PEN-014, PEN-015, PEN-016.
- Completed (P3): PEN-017, PEN-018, PEN-019, PEN-020, PEN-021, PEN-022.
- In progress: none.
- Next planned: backlog PEN-001..PEN-024 completed; next work should come from new user feedback/telemetry.

Implemented in current iteration:
- Normalized user-facing/transcription errors and progress messages to consistent English.
- Added structured session logging to `transcripts/logs/session_*.jsonl`.
- Introduced `ui_strings.py` and centralized user-facing texts used by GUI/config.
- Replaced legacy SendTo flow with output actions: `Open containing folder` and `Edit in Notepad`.
- Removed `send_to_service.py` and obsolete SendTo wiring from GUI.
- Improved YouTube download resilience: categorized yt-dlp errors, adaptive retry/strategy switching, and backoff for transient failures (`PEN-009`).
- Added Whisper model reuse across batch items via cached model loading and metadata flag `model_reused` (`PEN-007`).
- Added adaptive segmentation: skip ffmpeg split for short inputs and dynamic segment sizing based on duration/device (`PEN-008`).
- Added in-session YouTube metadata cache with TTL and integrated GUI lookups with cache-aware fetch path (`PEN-010`).
- Added per-stage operational timings to session logs (`item_done/item_error/batch_done` contexts) for download/transcription/export phases (`PEN-011`).
- Added persistent app settings (model/language/output/device/segment/run policy/timestamps) via `settings_service.py` (`PEN-012`).
- Added queue ergonomics: reorder up/down, retry failed, and run policy (`continue` vs `stop on first error`) (`PEN-013`).
- Added SRT/VTT export formats and timeline-aware subtitle generation (`PEN-014`).
- Added optional timestamps in TXT/MD outputs and richer timeline metadata in JSON (`PEN-015`).
- Added improved progress UX with stage labels and ETA formatting helpers (`PEN-016`).
- Introduced service-level modularization with `app_controller.py`, `queue_service.py`, `job_runner.py` (`PEN-017`).
- Added typed dataclasses for queue and run results in `models.py` (`PEN-018`).
- Added unit tests for queue/job runner/exporters/settings/youtube services (`PEN-019`).
- Added integration smoke tests for local and mocked YouTube flows (`PEN-020`).
- Added CI workflow (`.github/workflows/ci.yml`) for compile and test checks (`PEN-021`).
- Added release process docs and build scripts (`RELEASE.md`, `scripts/build.ps1`, `scripts/build.sh`) (`PEN-022`).

## 1. Goal
Build a more reliable, faster, and easier-to-use transcription app without changing its core flow:
- queue files/YouTube links
- run Whisper transcription
- export text output
- open output location quickly and edit transcript in Notepad

## 2. Current State (Quick Assessment)
- Core features work: local media, YouTube download, queue mode, output formats.
- Output actions are aligned with product direction: `Open containing folder` and `Edit in Notepad`.
- Settings persistence, queue reordering, retry-failed, and run-policy controls are implemented.
- SRT/VTT and timestamped TXT/MD exports are implemented.
- Automated tests and CI checks are available for core paths.
- Architecture has started to move from monolithic GUI into dedicated services, with room for further extraction.

## 3. Priority Roadmap

## P0 - Stabilize Core (1-2 weeks)
### 3.1 Text quality and consistency
- Standardize all UI/log messages to UTF-8-safe strings.
- Choose one UI language strategy (PL-only or PL/EN toggle) and apply consistently.
- Move user-facing strings to a central module (single source of truth).
Acceptance criteria:
- No mojibake in UI/logs.
- 100% visible strings loaded from one place.

### 3.2 Output action robustness
- Keep `Open containing folder` and `Edit in Notepad` actions predictable and fast.
- Detect and explain missing/removed transcript files before launching shell actions.
- Keep user-facing recovery hints short and actionable.
Acceptance criteria:
- Clear actionable message when transcript file no longer exists.
- Actions are disabled when no generated transcript file is available.

### 3.3 Error diagnostics and logging
- Add structured log file in app output folder (timestamped session logs).
- Include operation context (source, queue index, model, format, stage).
- Keep UI log concise, full details in file log.
Acceptance criteria:
- Every failed task has a traceable log entry in a file.
- Support can reproduce failures from logs alone.

### 3.4 Small technical cleanup
- Keep legacy SendTo references clearly marked as historical where needed.
- Keep button naming aligned with current UX (`Open containing folder`, `Edit in Notepad`).
- Remove unused email/send integration path from GUI if no longer part of the product direction.
- Add module docstrings and brief comments for non-obvious logic.
Acceptance criteria:
- No misleading names in GUI output action flow.
- Lint/grep shows no dead imports in active path.

## P1 - Performance and Throughput (2-4 weeks)
### 3.5 Batch performance
- Reuse Whisper model across items in one batch where settings match.
- Avoid repeated heavy initialization between queue items.
- Add optional "reuse model between files" toggle (on by default).
Acceptance criteria:
- Noticeably lower total batch time for 3+ files.
- No regression in output quality.

### 3.6 Smarter segmentation
- Skip ffmpeg segmentation for short files.
- Dynamically pick segment length by source duration and compute device.
- Keep cancellation responsive during segmentation/transcription.
Acceptance criteria:
- Fewer temporary segment files for short media.
- Stable memory usage and no worse cancellation behavior.

### 3.7 YouTube resilience
- Refine retry matrix and retry delays for transient yt-dlp failures.
- Cache fetched video info in-memory with expiration per session.
- Improve final error summary when all strategies fail.
Acceptance criteria:
- Better success rate for unstable links.
- Final failure messages identify root cause category.

## P2 - UX and Product Quality (3-6 weeks)
### 3.8 Settings persistence
- Save last-used settings (model, language, output dir, segment length, device).
- Restore settings on app start.
Acceptance criteria:
- App starts with last successful configuration by default.

### 3.9 Queue ergonomics
- Reorder queue items (up/down).
- Retry failed items in one click.
- Optional "stop on first error" and "continue on errors" modes.
Acceptance criteria:
- Users can manage long queues without re-adding files.

### 3.10 Output improvements
- Add SRT and VTT exporters.
- Optional timestamps in TXT/MD exports.
- Include richer metadata consistently across formats.
Acceptance criteria:
- SRT/VTT generated for each successful run.
- Export schema documented and stable.

### 3.11 Better progress UX
- Show per-item ETA and overall ETA.
- Distinguish stages: download, preprocess, transcribe, export.
Acceptance criteria:
- User can estimate finish time with reasonable accuracy.

## P3 - Engineering Scale and Distribution (6+ weeks)
### 3.12 Architecture refactor
- Split GUI controller into smaller services:
  - queue service
  - job runner
  - notification/log service
  - output-actions service (open folder / edit file)
- Introduce typed DTOs for queue items and run results.
Acceptance criteria:
- GUI module size reduced significantly.
- New features added without editing large monolithic blocks.

### 3.13 Test strategy
- Unit tests for:
  - format validation
  - output action availability logic (latest generated file handling)
  - exporter payload behavior
  - file open error mapping for folder/notepad actions
- Integration smoke tests for 1 local file and 1 mocked YouTube path.
Acceptance criteria:
- Basic test suite runs locally in under 2 minutes.
- Critical paths covered before release.

### 3.14 Packaging and release workflow
- Define repeatable build process (PyInstaller profile + version metadata).
- Add release checklist and artifact naming conventions.
- Optional auto-update check endpoint.
Acceptance criteria:
- One-command reproducible build for release artifacts.

## 4. Suggested Delivery Sequence
1. P0.1-P0.4 (stability and clarity first)
2. P1.5-P1.7 (performance and batch reliability)
3. P2.8-P2.11 (usability and output value)
4. P3.12-P3.14 (scale and release discipline)

## 5. Definition of Done (Program Level)
- No encoding artifacts in UI/logs.
- Output action flow is predictable and recoverable.
- Batch mode is faster and stable on at least 10 mixed items.
- Tests exist for critical logic and run in CI/local script.
- Release build process is documented and repeatable.

## 6. Risks and Mitigations
- Risk: YouTube behavior changes break download paths.
  - Mitigation: keep strategy matrix isolated in `youtube_service.py` and test quickly.
- Risk: Whisper model reuse introduces memory pressure.
  - Mitigation: add guard rails and fallback to per-item reload.
- Risk: Local shell/file association behavior differs by machine policy.
  - Mitigation: robust error mapping + guided recovery actions.
