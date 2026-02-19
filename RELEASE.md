# Release Guide

## 1. Preconditions
- Python 3.11 installed.
- `ffmpeg` available in `PATH`.
- Clean working tree and updated `BACKLOG.MD`/`IMPROVEMENTS.MD`.

## 2. Quality Gates
1. Run compile checks:
   - `python -m compileall .`
2. Run tests:
   - `python -m unittest discover -s tests -v`
3. Run a manual smoke check in GUI:
   - local file transcription
   - one YouTube URL transcription
   - output actions (`Open containing folder`, `Edit in Notepad`)

## 3. Build Artifacts
- Windows PowerShell:
  - `.\scripts\build.ps1`
- Linux/macOS shell:
  - `bash ./scripts/build.sh`

Default artifact naming convention:
- `Penman_<version>_<platform>.zip`
- Example: `Penman_0.1.0_windows.zip`

## 4. Release Checklist
1. Update version in release metadata/changelog.
2. Execute quality gates.
3. Build artifacts.
4. Validate artifact startup on a clean machine.
5. Publish artifacts and release notes.
6. Tag release in VCS.

## 5. Rollback
- Keep previous stable artifact available.
- If release fails smoke checks, do not publish; fix and rebuild.
