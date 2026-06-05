"""
version_manager.py
==================

Snapshot management for the lab scheduling project.

Each snapshot is a frozen copy of the planning output (CSV files + Daniel's
Excel files) at a specific point in time. Snapshots allow Daniel to:
  - View any past version of the planning
  - Restore a previous version if a manual edit went wrong
  - Compare two versions to see what changed

Storage layout:
    versions/
        YYYYMMDD_HHMMSS_label/
            metadata.json                    metadata about the snapshot
            optimized_schedule_v5.csv        main planning
            group_composition.csv            student-to-group mapping
            student_directory.csv            student lookup
            Curso_2025_2026/                 Excel deliverables
                Primero/...
                Segundo/...
                Tercero/...

Usage:
    import version_manager as vm

    # Create a snapshot after a pipeline run
    snap_id = vm.create_snapshot(
        snapshot_type='auto',
        description='Pipeline run with default config',
    )

    # List all snapshots, newest first
    for snap in vm.list_snapshots():
        print(snap['id'], snap['description'])

    # Restore a snapshot (replaces current outputs/)
    vm.restore_snapshot(snap_id)

    # Compare two snapshots
    diff = vm.compare_snapshots(snap_id_1, snap_id_2)
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional


# =============================================================================
# CONFIGURATION
# =============================================================================

VERSIONS_DIR = 'versions'

# Files included in every snapshot
SNAPSHOT_FILES = [
    'outputs/optimization/optimized_schedule_v5.csv',
    'outputs/optimization/optimized_schedule_v5.xlsx',
    'outputs/optimization/group_composition.csv',
    'outputs/optimization/student_directory.csv',
    'data_clean/optimization/student_busy.csv',
    'data_clean/optimization/lab_enrollments.csv',
]

# Directory included in every snapshot (Daniel's Excel deliverables)
SNAPSHOT_DIR = 'outputs/optimization/Curso_2025_2026'

MAX_SNAPSHOTS = 50   # keep only the 50 most recent snapshots (oldest auto-deleted)


# =============================================================================
# CORE API
# =============================================================================

def _sanitize_snapshot_id(label: str) -> str:
    """
    Sanitize a user-provided label into a safe directory name.

    Replaces spaces with underscores, removes unsafe characters, collapses
    multiple underscores. Returns a string suitable for use as a filesystem
    directory name on Windows, macOS and Linux.
    """
    import re
    # Replace common separators with underscore
    cleaned = re.sub(r'[\s/\\:]+', '_', label.strip())
    # Drop unsafe punctuation
    cleaned = re.sub(r'[^\w\-]', '', cleaned, flags=re.UNICODE)
    # Collapse multiple underscores
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    return cleaned[:80]   # keep filesystem-safe length


def _academic_year_short() -> str:
    """
    Return the current academic year in 'YY-YY' format.

    Academic year is assumed to start in September. So in May 2026 we are
    in academic year 2025-2026 → '25-26'.
    """
    now = datetime.now()
    if now.month >= 9:
        start_year = now.year
    else:
        start_year = now.year - 1
    return f"{start_year % 100:02d}-{(start_year + 1) % 100:02d}"


def _next_revision_number(prefix: str) -> int:
    """
    Return the next revision number for snapshots matching the given prefix.

    Scans the versions directory for entries that start with `prefix` and
    contain a `_revN` suffix, and returns the highest N + 1. Returns 1 if
    no such snapshots exist yet.
    """
    import re
    if not os.path.exists(VERSIONS_DIR):
        return 1
    pattern = re.compile(rf'^{re.escape(prefix)}_rev(\d+)$')
    max_rev = 0
    for entry in os.listdir(VERSIONS_DIR):
        match = pattern.match(entry)
        if match:
            max_rev = max(max_rev, int(match.group(1)))
    return max_rev + 1


def suggest_snapshot_name(snapshot_type: str = 'auto') -> str:
    """
    Build an intelligent default snapshot name following Daniel's convention.

    The convention is: `Distribucion_Practicas_YY-YY_revN`
    where YY-YY is the academic year and N is auto-incremented.

    For example, in May 2026 with 14 previous revisions:
        → 'Distribucion_Practicas_25-26_rev15'

    Args:
        snapshot_type: 'auto', 'manual', or 'milestone' — currently used
            only to select the prefix.

    Returns:
        A suggested name; the caller may edit it before calling
        `create_snapshot()`.
    """
    if snapshot_type == 'milestone':
        prefix = f"Distribucion_Practicas_{_academic_year_short()}"
    elif snapshot_type == 'manual':
        prefix = f"Edicion_Manual_{_academic_year_short()}"
    else:
        prefix = f"Distribucion_Practicas_{_academic_year_short()}"
    next_rev = _next_revision_number(prefix)
    return f"{prefix}_rev{next_rev}"


def create_snapshot(snapshot_type: str = 'auto',
                    description: str = '',
                    metrics: Optional[Dict] = None,
                    label: Optional[str] = None) -> Optional[str]:
    """
    Create a snapshot of the current planning state.

    Args:
        snapshot_type: 'auto' (after pipeline run) or 'manual' (before edit)
                       or 'milestone' (user-named checkpoint)
        description: human-readable label (e.g., "Before swapping Pedro to G3")
        metrics: optional dict of reliability metrics to attach
        label: optional snapshot ID — if provided, the snapshot directory
               will be named after this label (sanitized). If not provided,
               an intelligent default is generated following Daniel's
               convention (e.g. 'Distribucion_Practicas_25-26_rev15').

    Returns:
        Snapshot ID (e.g., 'Distribucion_Practicas_25-26_rev15') or None
        on failure.
    """
    if not os.path.exists('outputs/optimization/optimized_schedule_v5.csv'):
        # Nothing to snapshot
        return None

    # ─────────────────────────────────────────────────────
    # Generate the snapshot ID
    # ─────────────────────────────────────────────────────
    if label:
        # User provided a custom label → sanitize and use it
        base_id = _sanitize_snapshot_id(label)
        if not base_id:
            base_id = suggest_snapshot_name(snapshot_type)
    else:
        # No label → generate an intelligent default
        base_id = suggest_snapshot_name(snapshot_type)

    snapshot_id = base_id
    suffix = 0
    while os.path.exists(os.path.join(VERSIONS_DIR, snapshot_id)):
        suffix += 1
        snapshot_id = f"{base_id}_{suffix:02d}"
        if suffix > 99:
            return None   # safety bail-out
    snapshot_dir = os.path.join(VERSIONS_DIR, snapshot_id)

    try:
        os.makedirs(snapshot_dir, exist_ok=True)

        # Copy individual files
        files_copied = 0
        for file_path in SNAPSHOT_FILES:
            if os.path.exists(file_path):
                dest = os.path.join(snapshot_dir, os.path.basename(file_path))
                shutil.copy2(file_path, dest)
                files_copied += 1

        # Copy Curso_2025_2026 directory if present
        curso_copied = False
        if os.path.exists(SNAPSHOT_DIR):
            dest_curso = os.path.join(snapshot_dir, 'Curso_2025_2026')
            shutil.copytree(SNAPSHOT_DIR, dest_curso, dirs_exist_ok=True)
            curso_copied = True

        # Write metadata
        metadata = {
            'id':              snapshot_id,
            'created_at':      datetime.now().isoformat(),
            'snapshot_type':   snapshot_type,
            'description':     description or _default_description(snapshot_type),
            'files_count':     files_copied,
            'curso_included':  curso_copied,
        }
        if metrics:
            metadata['metrics'] = _make_metrics_json_safe(metrics)

        with open(os.path.join(snapshot_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # Cleanup old snapshots if limit exceeded
        _cleanup_old_snapshots()

        return snapshot_id

    except Exception as exc:
        # Best effort cleanup of partial snapshot
        if os.path.exists(snapshot_dir):
            try:
                shutil.rmtree(snapshot_dir)
            except Exception:
                pass
        print(f"  [WARN] Snapshot creation failed: {exc}")
        return None


def list_snapshots() -> List[Dict]:
    """
    List all snapshots, newest first.

    Returns:
        List of metadata dicts, ordered from newest to oldest.
    """
    if not os.path.exists(VERSIONS_DIR):
        return []

    snapshots = []
    for entry in os.listdir(VERSIONS_DIR):
        snap_dir = os.path.join(VERSIONS_DIR, entry)
        if not os.path.isdir(snap_dir):
            continue
        meta_path = os.path.join(snap_dir, 'metadata.json')
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            # Add disk size info
            meta['size_kb'] = _get_dir_size_kb(snap_dir)
            snapshots.append(meta)
        except Exception:
            continue

    # Sort by created_at, newest first
    snapshots.sort(key=lambda m: m.get('created_at', ''), reverse=True)
    return snapshots


def get_snapshot(snapshot_id: str) -> Optional[Dict]:
    """Return metadata for a single snapshot, or None if not found."""
    snap_dir = os.path.join(VERSIONS_DIR, snapshot_id)
    meta_path = os.path.join(snap_dir, 'metadata.json')
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        meta['size_kb'] = _get_dir_size_kb(snap_dir)
        return meta
    except Exception:
        return None


def restore_snapshot(snapshot_id: str, create_safety_snapshot: bool = True) -> bool:
    """
    Restore a snapshot, replacing the current outputs.

    Args:
        snapshot_id: ID of the snapshot to restore
        create_safety_snapshot: if True, snapshot the CURRENT state first
                                 (so you can undo the restore if needed)

    Returns:
        True on success, False on failure.
    """
    snap_dir = os.path.join(VERSIONS_DIR, snapshot_id)
    if not os.path.exists(snap_dir):
        print(f"  [FAIL] Snapshot {snapshot_id} not found")
        return False

    # Safety snapshot of current state before restoring
    if create_safety_snapshot:
        safety_id = create_snapshot(
            snapshot_type='auto',
            description=f'Auto-saved before restoring {snapshot_id}',
        )
        if safety_id:
            print(f"  [INFO] Current state saved as snapshot {safety_id}")

    try:
        # Restore individual files
        for file_path in SNAPSHOT_FILES:
            src = os.path.join(snap_dir, os.path.basename(file_path))
            if os.path.exists(src):
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                shutil.copy2(src, file_path)

        # Restore Curso_2025_2026 directory
        src_curso = os.path.join(snap_dir, 'Curso_2025_2026')
        if os.path.exists(src_curso):
            # Remove current Curso_2025_2026 directory first
            if os.path.exists(SNAPSHOT_DIR):
                shutil.rmtree(SNAPSHOT_DIR)
            shutil.copytree(src_curso, SNAPSHOT_DIR)

        return True

    except Exception as exc:
        print(f"  [FAIL] Restore failed: {exc}")
        return False


def delete_snapshot(snapshot_id: str) -> bool:
    """
    Permanently delete a snapshot.

    Args:
        snapshot_id: ID of the snapshot to delete

    Returns:
        True on success, False on failure.
    """
    snap_dir = os.path.join(VERSIONS_DIR, snapshot_id)
    if not os.path.exists(snap_dir):
        return False
    try:
        shutil.rmtree(snap_dir)
        return True
    except Exception as exc:
        print(f"  [FAIL] Delete failed: {exc}")
        return False


def update_description(snapshot_id: str, new_description: str) -> bool:
    """Update the human-readable description of a snapshot."""
    meta_path = os.path.join(VERSIONS_DIR, snapshot_id, 'metadata.json')
    if not os.path.exists(meta_path):
        return False
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        meta['description'] = new_description
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


# =============================================================================
# COMPARISON
# =============================================================================

def compare_snapshots(snap_id_a: str, snap_id_b: str) -> Optional[Dict]:
    """
    Compare two snapshots and return high-level differences.

    Args:
        snap_id_a: first snapshot ID (typically older)
        snap_id_b: second snapshot ID (typically newer)

    Returns:
        Dict with differences, or None if either snapshot missing.
    """
    import pandas as pd

    schedule_a_path = os.path.join(VERSIONS_DIR, snap_id_a, 'optimized_schedule_v5.csv')
    schedule_b_path = os.path.join(VERSIONS_DIR, snap_id_b, 'optimized_schedule_v5.csv')

    if not (os.path.exists(schedule_a_path) and os.path.exists(schedule_b_path)):
        return None

    try:
        df_a = pd.read_csv(schedule_a_path)
        df_b = pd.read_csv(schedule_b_path)
    except Exception:
        return None

    # Compute high-level differences
    diff = {
        'snap_a':            snap_id_a,
        'snap_b':            snap_id_b,
        'sessions_a':        len(df_a),
        'sessions_b':        len(df_b),
        'sessions_diff':     len(df_b) - len(df_a),
        'groups_a':          df_a.groupby(['subject', 'grupo']).ngroups if len(df_a) else 0,
        'groups_b':          df_b.groupby(['subject', 'grupo']).ngroups if len(df_b) else 0,
        'subjects_changed':  [],
        'cells_changed':     0,
    }

    # Find sessions that changed (same subject+grupo+session, different week/day/block/room)
    if len(df_a) and len(df_b):
        try:
            key_cols = ['subject', 'grupo', 'session']
            value_cols = ['week', 'day', 'time_block', 'lab_rooms']

            # Build keyed dicts
            map_a = df_a.set_index(key_cols)[value_cols].to_dict('index')
            map_b = df_b.set_index(key_cols)[value_cols].to_dict('index')

            common_keys = set(map_a.keys()) & set(map_b.keys())
            changed = 0
            subjects_changed = set()
            for k in common_keys:
                if map_a[k] != map_b[k]:
                    changed += 1
                    subjects_changed.add(k[0])
            diff['cells_changed'] = changed
            diff['subjects_changed'] = sorted(subjects_changed)

            # Sessions added/removed
            diff['sessions_added'] = len(set(map_b.keys()) - set(map_a.keys()))
            diff['sessions_removed'] = len(set(map_a.keys()) - set(map_b.keys()))
        except Exception:
            pass

    return diff


# =============================================================================
# INTERNAL HELPERS
# =============================================================================

def _default_description(snapshot_type: str) -> str:
    """Default human-readable description if none provided."""
    if snapshot_type == 'auto':
        return f"Génération automatique - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    elif snapshot_type == 'manual':
        return f"Modification manuelle - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    elif snapshot_type == 'milestone':
        return f"Étape importante - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    else:
        return f"Snapshot - {datetime.now().strftime('%d/%m/%Y %H:%M')}"


def _get_dir_size_kb(directory: str) -> int:
    """Compute total size of a directory in KB."""
    total_bytes = 0
    for dirpath, _, filenames in os.walk(directory):
        for fname in filenames:
            try:
                total_bytes += os.path.getsize(os.path.join(dirpath, fname))
            except Exception:
                pass
    return total_bytes // 1024


def _cleanup_old_snapshots() -> int:
    """
    Delete oldest snapshots if total count exceeds MAX_SNAPSHOTS.

    Returns:
        Number of snapshots deleted.
    """
    snapshots = list_snapshots()
    if len(snapshots) <= MAX_SNAPSHOTS:
        return 0

    # Sort newest first; older ones (after MAX_SNAPSHOTS) are deletable
    deletable = snapshots[MAX_SNAPSHOTS:]
    deleted_count = 0
    for snap in deletable:
        # Don't delete milestones (user-named)
        if snap.get('snapshot_type') == 'milestone':
            continue
        if delete_snapshot(snap['id']):
            deleted_count += 1
    return deleted_count


def _make_metrics_json_safe(obj):
    """Recursively convert metrics dict to JSON-safe primitives."""
    if isinstance(obj, dict):
        return {k: _make_metrics_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_metrics_json_safe(x) for x in obj]
    elif hasattr(obj, 'item'):  # numpy scalar
        return obj.item()
    elif obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    else:
        return str(obj)


# =============================================================================
# CLI (for testing)
# =============================================================================

def main():
    """Quick CLI for testing the version manager."""
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python version_manager.py list")
        print("  python version_manager.py snapshot [description]")
        print("  python version_manager.py restore <id>")
        print("  python version_manager.py delete <id>")
        return

    cmd = sys.argv[1]

    if cmd == 'list':
        snaps = list_snapshots()
        print(f"\n{len(snaps)} snapshot(s):\n")
        for s in snaps:
            print(f"  {s['id']}  [{s.get('snapshot_type', '?'):>8s}]  "
                  f"{s.get('size_kb', 0)} KB  {s.get('description', '')}")
    elif cmd == 'snapshot':
        desc = sys.argv[2] if len(sys.argv) > 2 else ''
        snap_id = create_snapshot(snapshot_type='manual', description=desc)
        if snap_id:
            print(f"  [OK] Snapshot created: {snap_id}")
        else:
            print(f"  [FAIL] Could not create snapshot")
    elif cmd == 'restore' and len(sys.argv) > 2:
        if restore_snapshot(sys.argv[2]):
            print(f"  [OK] Restored snapshot {sys.argv[2]}")
        else:
            print(f"  [FAIL] Restore failed")
    elif cmd == 'delete' and len(sys.argv) > 2:
        if delete_snapshot(sys.argv[2]):
            print(f"  [OK] Deleted snapshot {sys.argv[2]}")
        else:
            print(f"  [FAIL] Delete failed")
    else:
        print("Unknown command")


if __name__ == '__main__':
    main()