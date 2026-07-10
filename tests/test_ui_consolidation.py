"""Tests for the Phase 2/3 UI consolidation.

Ensures the reusable UI components exist, expose their render entry points,
and that the standalone pages they replace are gone (single Configuration
page / single Export page), while the polished simulator page remains.
"""

from __future__ import annotations

import ast
import importlib
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_ui_solver_constraints_module_exposes_render():
    mod = importlib.import_module("ui_solver_constraints")
    assert callable(getattr(mod, "render_solver_constraints_section", None))


def test_ui_advanced_exports_module_exposes_render():
    mod = importlib.import_module("ui_advanced_exports")
    assert callable(getattr(mod, "render_advanced_exports_section", None))


def test_old_standalone_pages_removed():
    # All standalone Streamlit multipage entries are consolidated into the
    # single radio navigation; the pages/ directory should no longer exist
    # (or at least contain none of the old standalone files).
    pages_dir = os.path.join(ROOT, "pages")
    pages = os.listdir(pages_dir) if os.path.isdir(pages_dir) else []
    assert "4_Configuration_Solveur.py" not in pages
    assert "6_Exports_Avanc\u00e9s.py" not in pages
    assert "5_Simulateur_Infaisabilite.py" not in pages
    assert "4_Simulateur_Infaisabilite.py" not in pages


def test_simulator_is_render_module():
    # The infeasibility simulator is now a render() module wired into the
    # main navigation, not a separate multipage file.
    mod = importlib.import_module("ui_infeasibility")
    assert callable(getattr(mod, "render", None))
    path = os.path.join(ROOT, "ui_infeasibility.py")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    ast.parse(source)  # must be valid Python
    # Polished ordering: summary and suggestions come before manual scenarios.
    assert source.index("Etat du dernier run") < source.index(
        "1. Suggestions automatiques")
    assert source.index("1. Suggestions automatiques") < source.index(
        "2. Simulation manuelle : exclure des groupes")


def test_app_embeds_simulator():
    with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fh:
        source = fh.read()
    assert "ui_infeasibility" in source
    assert "nav_simulateur" in source


def test_app_embeds_consolidated_components():
    with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fh:
        source = fh.read()
    assert "render_solver_constraints_section" in source
    assert "render_advanced_exports_section" in source
    assert "Contraintes du solveur" in source


def test_spec_bundles_new_ui_modules():
    with open(os.path.join(ROOT, "LabScheduling.spec"), encoding="utf-8") as fh:
        spec = fh.read()
    assert "ui_solver_constraints" in spec
    assert "ui_advanced_exports" in spec
