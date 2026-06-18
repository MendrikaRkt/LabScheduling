"""Tests du calcul des KPIs (Étape 6.6)."""

import kpi_report as kr


def test_compute_kpis_groups_and_placement(synthetic_results_df,
                                           synthetic_groups):
    dq = {"grouping": {"total_enrolled": 7, "total_placed": 6,
                       "total_unplaced": 1, "global_placement_pct": 85.7}}
    kpi = kr.compute_kpis(synthetic_results_df, synthetic_groups, dq)
    assert kpi["groups"]["total"] == 2
    assert kpi["groups"]["overflow"] == 1
    assert kpi["groups"]["recovered"] == 1
    assert kpi["placement"]["unplaced"] == 1
    assert kpi["placement"]["placement_pct"] == 85.7


def test_compute_kpis_day_balance_tracks_friday(synthetic_results_df,
                                                synthetic_groups):
    kpi = kr.compute_kpis(synthetic_results_df, synthetic_groups)
    assert "day_balance" in kpi
    assert kpi["friday_sessions"] == 1  # une séance Mat B le Viernes
    assert kpi["total_sessions"] == 3


def test_compute_kpis_room_occupancy(synthetic_results_df, synthetic_groups):
    kpi = kr.compute_kpis(synthetic_results_df, synthetic_groups)
    assert "room_sessions" in kpi
    assert kpi["room_sessions"].get("Lab Alpha") == 2


def test_compute_kpis_solver_summary(synthetic_results_df, synthetic_groups):
    runs = [
        {"semester": 1, "status": "OPTIMAL", "n_sessions": 2,
         "wall_time_s": 1.5, "objective": 100.0, "gap": 0.0},
        {"semester": 2, "status": "FEASIBLE", "n_sessions": 1,
         "wall_time_s": 3.2, "objective": 50.0, "gap": 0.01, "recovered": True},
    ]
    kpi = kr.compute_kpis(synthetic_results_df, synthetic_groups,
                          solver_runs=runs)
    s = kpi["solver_summary"]
    assert s["runs"] == 2
    assert s["optimal"] == 1
    assert s["feasible"] == 1
    assert s["max_wall_time_s"] == 3.2


def test_compute_kpis_robust_to_empty():
    kpi = kr.compute_kpis(None, [])
    assert kpi["groups"]["total"] == 0
    # ne doit pas planter et reste rendu en texte
    txt = kr.render_text(kpi)
    assert "RAPPORT KPI" in txt


def test_render_text_contains_sections(synthetic_results_df, synthetic_groups):
    kpi = kr.compute_kpis(synthetic_results_df, synthetic_groups)
    txt = kr.render_text(kpi)
    assert "Groupes" in txt
    assert "Équilibrage par jour" in txt
