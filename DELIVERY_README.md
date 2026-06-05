# Lab Scheduling — App v1 delivery

This folder is the complete kit to build the Windows app and contains the
patched application. Below is exactly what changed and what to do next.

## What was fixed / added

1. **Navigation double-click — fixed.**
   The Prev/Next wizard buttons set the target page but never forced a rerun,
   so the sidebar (which renders before the page body) only reacted on the
   *next* click. Added `st.rerun()` to `wizard_nav()` → one click now navigates.

2. **Persistent memory — added** (`persistence.py`).
   Language, theme and the advanced configuration are saved and restored
   automatically; every optimisation run is logged. Stored per-user under
   `%APPDATA%\LabScheduling\` (works even when the app is installed in the
   read-only `Program Files`). A “Recent runs” panel on the Home page shows the
   history — visible proof that memory survives restarts.

3. **Dark theme — fixed.**
   The dark-mode CSS used an invalid selector (`html[data-theme="dark"] :root`,
   which can never match) so in-app theme switching didn’t recolour anything.
   Corrected to target the element directly; verified by rendering.

4. **Text alignment polish.**
   Conflict-detail lists that were emitted one `st.write` per line (with stray
   leading spaces) are now single, properly-aligned Markdown blocks.

5. **Design reviewed against real renders.**
   The component CSS (sidebar, hero, cards, headers, badges) was rendered in
   light and dark and is clean and on-brand — no oversized images (all logos
   are CSS-sized; the app uses no raw `st.image`).

## Build the `.exe`

A Windows `.exe` must be built on Windows (PyInstaller does not cross-compile).
See **`BUILD_INSTRUCTIONS.md`** — in short: install Python 3.11/3.12 + Inno
Setup, then run **`build.bat`**. You get:

- `Output\LabScheduling_Setup_v1.0.0.exe` (installer)
- `dist\LabScheduling\LabScheduling.exe` (portable)

## ⚠️ Two placeholders to replace before shipping

- **`assets/loyola_logo.png`** and **`assets/app_icon.ico`** are placeholders I
  generated for testing the layout. Replace them with the official Loyola logo
  and an icon before building, keeping the same filenames.

## Files in this kit

| File | Role |
|------|------|
| `app.py` | The patched Streamlit application |
| `persistence.py` | Persistent-memory module (new) |
| `pipeline.py` | The 100 %/100-reliability optimisation pipeline |
| `reliability_metrics.py` | Reliability scoring (override-aware) |
| `version_manager.py` | Snapshot/version history |
| `manual_edit.py` | Manual-edit feasibility checks |
| `run_app.py` | Desktop launcher (entry point for the .exe) |
| `LabScheduling.spec` | PyInstaller build spec |
| `installer.iss` | Inno Setup installer script |
| `build.bat` | One-click Windows build |
| `requirements.txt` | Pinned dependencies |
| `BUILD_INSTRUCTIONS.md` | Full build guide + troubleshooting |
| `assets/` | Logo + icon (placeholders) |

All `.py` files were smoke-tested: every one of the 12 pages executes without
error, and `persistence.py` round-trips preferences and run history.
