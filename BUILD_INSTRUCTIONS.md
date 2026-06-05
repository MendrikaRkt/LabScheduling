# Building the Windows `.exe` — Lab Scheduling Automation v1.0.0

## Important: why this must be built on Windows

A Windows `.exe` can only be produced **on a Windows machine**. PyInstaller does
not cross-compile: run on Linux/macOS it emits a binary for *that* platform, not
a Windows executable. This kit gives you everything to build the `.exe` in one
step on your Windows PC.

You do **not** need to write any code — just install two tools once, then run
`build.bat`.

---

## One-time prerequisites

1. **Python 3.11 or 3.12 (64-bit)** — https://www.python.org/downloads/
   During install, tick **“Add python.exe to PATH”**.
2. **Inno Setup 6** (only needed for the single-file installer) —
   https://jrsoftware.org/isdl.php

---

## Build in one click

1. Put all the files from this kit in one folder:

   ```
   app.py
   run_app.py
   pipeline.py
   reliability_metrics.py
   version_manager.py
   manual_edit.py
   persistence.py
   requirements.txt
   LabScheduling.spec
   installer.iss
   build.bat
   assets\loyola_logo.png
   assets\app_icon.ico
   config\            (optional: a default user_config.json)
   data_clean\        (optional: reference data to ship pre-loaded)
   ```

2. Double-click **`build.bat`** (or run it from a terminal).

   It will:
   - create a virtual environment and install the dependencies,
   - run PyInstaller (`LabScheduling.spec`),
   - run Inno Setup to produce the installer.

3. Collect your outputs:
   - **Installer:** `Output\LabScheduling_Setup_v1.0.0.exe` — give this to Daniel.
   - **Portable app:** `dist\LabScheduling\LabScheduling.exe` — runs without installing.

Double-clicking `LabScheduling.exe` starts a local server and opens the app in
the default browser. Closing the console window stops it.

---

## Where the app stores data (persistent memory)

Because `Program Files` is read-only, the app keeps everything writable under
the user profile:

```
%APPDATA%\LabScheduling\
    prefs.json            language, theme, advanced configuration
    runs.json             history of past optimisation runs
    workspace\            outputs, config, data_clean, snapshots
```

Language, configuration and run history are restored automatically on the next
launch — that is the persistent memory. To reset the app to a clean state,
delete the `%APPDATA%\LabScheduling` folder.

---

## Troubleshooting

- **A traceback flashes and the window closes.** Build a debug version: in
  `LabScheduling.spec` set `console=True`, rebuild with
  `pyinstaller LabScheduling.spec --noconfirm`, run
  `dist\LabScheduling\LabScheduling.exe` from a terminal and read the error.
- **`ModuleNotFoundError` at runtime.** Add the missing module name to
  `hiddenimports` in `LabScheduling.spec` and rebuild.
- **Streamlit “missing static files”.** The spec already does
  `collect_all("streamlit")`; make sure you built inside the virtual
  environment created by `build.bat` (so the bundled Streamlit matches
  `requirements.txt`).
- **`pip` cannot find a wheel** for your exact Python: relax the version pin in
  `requirements.txt` (drop the patch number).
- **Antivirus flags the fresh `.exe`.** This is a common false positive for
  unsigned PyInstaller binaries. Code-sign the executable, or add an exclusion.

---

## Updating the app later

Re-run `build.bat` after editing any `.py` file. Bump the version in
`installer.iss` (`MyAppVersion`) so the installer filename reflects the new
release.
