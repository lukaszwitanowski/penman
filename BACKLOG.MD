# TECHNICAL BACKLOG - Penman

## Estimation Model
- `SP` (Story Points): complexity/uncertainty scale.
- `ETA`: expected engineering effort for one developer.
- Priority scale: `P0` (critical) -> `P3` (long-term).
- Status:
  - `Done` - completed and verified
  - `In progress` - partially implemented
  - `Planned` - not started

## Backlog Items
| ID | Priority | Task | Scope (files) | Dependencies | Estimate | Status |
|---|---|---|---|---|---|---|
| PEN-001 | P0 | Normalize UI/log strings and remove encoding artifacts | `gui.py`, `transcription_service.py`, `youtube_service.py`, `legacy: send_to_service.py`, `exporters.py` | None | 5 SP / 1-2d | Done |
| PEN-002 | P0 | Centralize user-facing strings (single module for texts) | `gui.py`, `config.py`, `new: ui_strings.py` | PEN-001 | 8 SP / 2-3d | Done |
| PEN-003 | P0 | Rename send button internals (`send_email_button` -> `send_to_button`) and cleanup dead email references in GUI flow (legacy, superseded by PEN-023) | `gui.py` | None | 2 SP / 0.5d | Done |
| PEN-004 | P0 | Improve SendTo diagnostics (explicit handling for code 31, recovery hints) (legacy, superseded by PEN-023/PEN-024) | `send_to_service.py`, `gui.py` | PEN-003 | 3 SP / 0.5-1d | Done |
| PEN-005 | P0 | Add session log file (structured, timestamped) | `gui.py`, `new: logging_service.py` | PEN-001 | 5 SP / 1-2d | Done |
| PEN-006 | P0 | Add "Open SendTo folder" action for recovery (legacy, superseded by PEN-023/PEN-024) | `send_to_service.py`, `gui.py` | PEN-004 | 2 SP / 0.5d | Done |
| PEN-023 | P0 | Replace SendTo action with output actions (`Open containing folder`, `Edit in Notepad`) | `gui.py`, `ui_strings.py` | PEN-002 | 3 SP / 0.5-1d | Done |
| PEN-024 | P0 | Remove legacy SendTo module and dead references | `removed: send_to_service.py`, `gui.py`, `IMPROVEMENTS.MD`, `BACKLOG.MD` | PEN-023 | 2 SP / 0.5d | Done |
| PEN-007 | P1 | Reuse Whisper model across batch items | `transcription_service.py`, `gui.py` | PEN-005 | 13 SP / 3-5d | Done |
| PEN-008 | P1 | Adaptive segmentation (skip for short input, dynamic segment length) | `transcription_service.py` | PEN-007 | 8 SP / 2-3d | Done |
| PEN-009 | P1 | Improve YouTube retry strategy and error classification | `youtube_service.py` | None | 8 SP / 2-3d | Done |
| PEN-010 | P1 | Add in-session cache for YouTube metadata with TTL | `youtube_service.py`, `gui.py` | PEN-009 | 3 SP / 1d | Done |
| PEN-011 | P1 | Add operational metrics (per-stage timings in logs) | `gui.py`, `transcription_service.py`, `youtube_service.py` | PEN-005 | 5 SP / 1-2d | Done |
| PEN-012 | P2 | Persist settings (model/lang/output/device/segment) | `gui.py`, `config.py`, `new: settings_service.py` | PEN-002 | 8 SP / 2-3d | Done |
| PEN-013 | P2 | Queue reorder controls (up/down), retry failed, run policy switches | `gui.py` | None | 8 SP / 2-3d | Done |
| PEN-014 | P2 | Add SRT and VTT exporters | `exporters.py`, `transcription_service.py`, `config.py` | None | 5 SP / 1-2d | Done |
| PEN-015 | P2 | Optional timestamps in TXT/MD export | `exporters.py` | PEN-014 | 3 SP / 1d | Done |
| PEN-016 | P2 | Improve progress UX (stage labels + item/global ETA) | `gui.py`, `transcription_service.py`, `youtube_service.py` | PEN-011 | 8 SP / 2-3d | Done |
| PEN-017 | P3 | Refactor monolithic GUI into coordinator/services | `gui.py`, `new: app_controller.py`, `new: queue_service.py`, `new: job_runner.py` | PEN-002, PEN-013 | 13 SP / 4-6d | Done |
| PEN-018 | P3 | Introduce typed DTOs/dataclasses for queue items and run results | `gui.py`, `transcription_service.py`, `youtube_service.py`, `new: models.py` | PEN-017 | 5 SP / 1-2d | Done |
| PEN-019 | P3 | Add unit tests for critical logic | `new: tests/*` | PEN-002, PEN-018 | 13 SP / 4-6d | Done |
| PEN-020 | P3 | Add integration smoke tests (local + mocked YouTube) | `new: tests/*` | PEN-019 | 8 SP / 2-3d | Done |
| PEN-021 | P3 | Add CI workflow (lint + tests + build checks) | `.github/workflows/*`, test config files | PEN-019 | 5 SP / 1-2d | Done |
| PEN-022 | P3 | Release pipeline and packaging checklist | `PLAN.md`, `new: RELEASE.md`, build scripts | PEN-021 | 5 SP / 1-2d | Done |

## Sprint Proposal (Example)
### Sprint 1 (P0 hardening)
- PEN-001, PEN-003, PEN-004, PEN-005, PEN-006
- Target: stabilize messaging + observability + legacy SendTo reliability

### Sprint 2 (P0 completion + UX pivot + P1 start)
- PEN-002, PEN-023, PEN-024, PEN-009, PEN-010
- Target: complete UX text layer, switch from SendTo to output-file actions, and improve YouTube resilience

### Sprint 3 (Performance)
- PEN-007, PEN-008, PEN-011
- Target: faster and more predictable batch execution

### Sprint 4 (UX and output)
- PEN-012, PEN-013, PEN-014, PEN-015, PEN-016
- Target: better daily usability and richer export formats

### Sprint 5+ (Scale and release)
- PEN-017, PEN-018, PEN-019, PEN-020, PEN-021, PEN-022
- Target: maintainable architecture and release discipline

## Progress Snapshot (2026-02-19)
- Done: PEN-001, PEN-002, PEN-003, PEN-004, PEN-005, PEN-006, PEN-007, PEN-008, PEN-009, PEN-010, PEN-011, PEN-012, PEN-013, PEN-014, PEN-015, PEN-016, PEN-017, PEN-018, PEN-019, PEN-020, PEN-021, PEN-022, PEN-023, PEN-024.
- In progress: none.
- Planned: none.

## Immediate Next 3 Tasks
1. Backlog completed for PEN-001..PEN-024.
2. Collect user feedback from real workloads and triage new items.
3. Prioritize follow-up hardening based on logs/tests telemetry.
