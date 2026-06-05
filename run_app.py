"""
run_app.py — Desktop launcher for the Lab Scheduling app.

This is the entry point PyInstaller turns into LabScheduling.exe. It:
  1. Resolves a WRITABLE workspace (the install folder under Program Files is
     read-only), so the app's relative paths (outputs/, config/, data_clean/)
     and the version snapshots all land in a per-user location.
  2. Copies the bundled read-only resources (assets, default config, the
     reference data files if shipped) into that workspace on first launch.
  3. Suppresses Streamlit's first-run e-mail prompt.
  4. Boots Streamlit on a local port and opens the default browser.

Works both frozen (PyInstaller, sys.frozen=True, resources under sys._MEIPASS)
and from source (python run_app.py during development).
"""

import os
import sys
import time
import shutil
import threading
import webbrowser
from pathlib import Path

APP_NAME = "LabScheduling"
PORT = 8501


# ────────────────────────────────────────────────────────────
# Resource / workspace resolution
# ────────────────────────────────────────────────────────────
def resource_base() -> Path:
    """Folder that contains the bundled app.py and resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return Path(__file__).resolve().parent


def workspace_dir() -> Path:
    """Per-user writable workspace; everything the app reads/writes lives here."""
    override = os.environ.get("LABSCHED_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"
    ws = base / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _bundle_version(res: Path) -> str:
    """Read the build version from the bundled VERSION.txt (fallback 0.0.0)."""
    try:
        vf = res / "VERSION.txt"
        if vf.exists():
            return vf.read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        pass
    return "0.0.0"


def _parse_ver(v: str) -> tuple:
    import re
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def seed_workspace(res: Path, ws: Path) -> None:
    """Seed bundled resources into the writable workspace, version-aware.

    Key design (so you never have to delete %APPDATA% by hand again):

      • REFERENCE files shipped with the app — assets (logo/icon), the default
        config, and reference data such as subject_supervision.csv — are
        REFRESHED from the bundle whenever the installed build version is newer
        than the version that last seeded this workspace. This is what makes a
        new build's logo / reference data appear automatically.

      • USER data — the user's own config edits, run history (prefs.json /
        runs.json), and generated outputs/ — are NEVER overwritten. Only gaps
        are filled on a fresh workspace.

    A marker file `.seed_version` records which build version last seeded the
    workspace, so the refresh runs exactly once per upgrade.
    """
    # Ensure the directory skeleton exists
    for sub in ("outputs", "outputs/optimization", "config", "data_clean",
                "data_clean/optimization", "assets"):
        (ws / sub).mkdir(parents=True, exist_ok=True)

    bundle_ver = _bundle_version(res)
    marker = ws / ".seed_version"
    seeded_ver = ""
    try:
        if marker.exists():
            seeded_ver = marker.read_text(encoding="utf-8").strip()
    except Exception:
        seeded_ver = ""

    # Refresh when the bundle is newer than what last seeded this workspace
    # (or when the workspace has never been seeded).
    refresh = (not seeded_ver) or (_parse_ver(bundle_ver) > _parse_ver(seeded_ver))

    def _copy_tree(subdir: str, *, overwrite: bool):
        """Copy res/<subdir> → ws/<subdir>. If overwrite, replace existing
        files; otherwise only copy missing ones."""
        src = res / subdir
        if not src.is_dir():
            return
        for root, _dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            dest_dir = (ws / subdir) if rel == "." else (ws / subdir / rel)
            dest_dir.mkdir(parents=True, exist_ok=True)
            for fn in files:
                dest = dest_dir / fn
                if overwrite or not dest.exists():
                    try:
                        shutil.copy2(os.path.join(root, fn), dest)
                    except Exception:
                        pass

    # REFERENCE resources: refreshed on upgrade, gap-filled otherwise.
    _copy_tree("assets", overwrite=refresh)
    _copy_tree("data_clean", overwrite=refresh)

    # Default config: only ever fill the gap. The user's own config must never
    # be clobbered by an upgrade, so this is always gap-fill (never overwrite).
    _copy_tree("config", overwrite=False)

    # ── Self-heal a known folder TYPO ────────────────────────────────────────
    # Some workspaces ended up with a misspelled 'optimizarion' folder (an 'r'
    # instead of 't'), so files placed there (e.g. subject_professors.csv) were
    # invisible to the app. Migrate anything from '<base>/optimizarion' into the
    # correct '<base>/optimization', then drop the empty typo folder.
    for _base in ("data_clean", "outputs"):
        _typo = ws / _base / "optimizarion"
        _right = ws / _base / "optimization"
        if _typo.is_dir():
            try:
                _right.mkdir(parents=True, exist_ok=True)
                for _f in _typo.iterdir():
                    _dest = _right / _f.name
                    if not _dest.exists():
                        shutil.move(str(_f), str(_dest))
                # remove the typo folder if now empty
                try:
                    _typo.rmdir()
                except OSError:
                    pass
            except Exception:
                pass

    # Record the version that seeded this workspace.
    if refresh:
        try:
            marker.write_text(bundle_ver, encoding="utf-8")
        except Exception:
            pass


def _seed_workspace_legacy(res: Path, ws: Path) -> None:
    """Copy bundled read-only resources into the writable workspace once."""
    # Directories the app expects to exist and write into
    for sub in ("outputs", "outputs/optimization", "config", "data_clean", "assets"):
        (ws / sub).mkdir(parents=True, exist_ok=True)

    # Copy bundled assets (logo, etc.) if the workspace doesn't have them yet
    src_assets = res / "assets"
    if src_assets.is_dir():
        for f in src_assets.iterdir():
            dest = ws / "assets" / f.name
            if f.is_file() and not dest.exists():
                try:
                    shutil.copy2(f, dest)
                except Exception:
                    pass

    # Copy a bundled default config if present and none exists yet
    src_cfg = res / "config"
    if src_cfg.is_dir():
        for f in src_cfg.iterdir():
            dest = ws / "config" / f.name
            if f.is_file() and not dest.exists():
                try:
                    shutil.copy2(f, dest)
                except Exception:
                    pass

    # Seed bundled reference data (e.g. subject_supervision.csv used to show the
    # professor in Vista profesor). Copy RECURSIVELY so data_clean/optimization/
    # is included, and only fill gaps (never overwrite a file the pipeline has
    # already regenerated in the workspace).
    src_data = res / "data_clean"
    if src_data.is_dir():
        for root, _dirs, files in os.walk(src_data):
            rel_root = os.path.relpath(root, src_data)
            dest_dir = ws / "data_clean" if rel_root == "." else ws / "data_clean" / rel_root
            dest_dir.mkdir(parents=True, exist_ok=True)
            for fn in files:
                dest = dest_dir / fn
                if not dest.exists():
                    try:
                        shutil.copy2(os.path.join(root, fn), dest)
                    except Exception:
                        pass


def silence_first_run(res_home: Path) -> None:
    """Write a Streamlit credentials file so the e-mail prompt never blocks."""
    st_dir = Path.home() / ".streamlit"
    try:
        st_dir.mkdir(parents=True, exist_ok=True)
        cred = st_dir / "credentials.toml"
        if not cred.exists():
            cred.write_text('[general]\nemail = ""\n', encoding="utf-8")
    except Exception:
        pass


def open_browser_when_ready() -> None:
    import urllib.request
    url = f"http://localhost:{PORT}"
    for _ in range(60):
        try:
            if urllib.request.urlopen(url + "/_stcore/health", timeout=2).status == 200:
                break
        except Exception:
            time.sleep(1)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> int:
    res = resource_base()
    ws = workspace_dir()
    seed_workspace(res, ws)
    silence_first_run(res)

    # Make the per-user data dir explicit for the persistence module
    os.environ.setdefault("LABSCHED_DATA_DIR", str(ws.parent))

    # All relative paths in app.py / version_manager.py now resolve here
    os.chdir(ws)

    # Ensure bundled modules (pipeline, reliability_metrics, ...) are importable
    if str(res) not in sys.path:
        sys.path.insert(0, str(res))

    # Activate Python patches (Channel A updates) BEFORE the app imports its
    # modules, so any patched .py shadows the bundled version. Best-effort.
    #
    # IMPORTANT: `streamlit run app.py` spawns a SEPARATE process that does not
    # inherit this process's sys.path. So we must (a) launch the PATCHED app.py
    # if one exists, and (b) pass the patch dir to that child via PYTHONPATH so
    # patched modules (pipeline.py, excel_export.py, …) shadow the bundled ones.
    patched_app = None
    patch_dir = None
    try:
        import update_manager
        patch_dir = update_manager.activate_patches()  # adds to THIS proc path
        if patch_dir:
            print(f"[update] active patches: {patch_dir} "
                  f"(effective version {update_manager.effective_version()})")
            cand = os.path.join(patch_dir, "app.py")
            if os.path.exists(cand):
                patched_app = cand
    except Exception as _e:
        print(f"[update] patch activation skipped: {_e}")

    # Choose which app.py Streamlit will run: the patched one if present.
    app_path = patched_app or str(res / "app.py")

    # Propagate the import search path to the Streamlit CHILD process so it
    # resolves patched modules first, then the bundle root. PyInstaller's
    # frozen sys.path is reconstructed in the child, so we prepend via env.
    _pp_parts = []
    if patch_dir:
        _pp_parts.append(patch_dir)
    _pp_parts.append(str(res))
    existing_pp = os.environ.get("PYTHONPATH", "")
    if existing_pp:
        _pp_parts.append(existing_pp)
    os.environ["PYTHONPATH"] = os.pathsep.join(_pp_parts)

    # Streamlit server options tuned for a local desktop session
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_ADDRESS"] = "127.0.0.1"  # loopback only - not reachable from the LAN
    os.environ["STREAMLIT_SERVER_PORT"] = str(PORT)
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"  # we open the browser ourselves
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    threading.Thread(target=open_browser_when_ready, daemon=True).start()

    import streamlit.web.cli as stcli
    sys.argv = [
        "streamlit", "run", app_path,
        "--server.address=127.0.0.1",
        f"--server.port={PORT}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--global.developmentMode=false",
    ]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())