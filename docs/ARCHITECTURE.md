# LabScheduling — Architecture and Pipeline Map

Status: living document. Scope: the full system from raw data ingestion to Excel
export, the solver core, the diagnostics layer, and the roadmap for scaling the
engine beyond the university lab use case (exam scheduling, an AI university
agent via API/MCP, other assignment/scheduling problems).

The core idea of the project: build a general **optimization and planning
engine**. The current context is university lab scheduling, but the engine is
meant to be reusable as an extension for similar constrained assignment problems.

---

## 1. The engine in one sentence

Given students, their course enrollments, professor teaching assignments, the
official course timetable, room capacities and the academic calendar, the engine
produces a **valid, balanced weekly lab schedule**: which group meets on which
day / time block / room / week, who supervises it, and how many credits each
professor spends — while flagging every incoherence instead of hiding it.

Guiding principle, preserved everywhere in the codebase:

> "Assignment is data; the system validates it, it does not decide it."
> (Signal, do not fabricate.)

---

## 2. Optimization method (the honest answer)

The engine is **hybrid: heuristic group formation + CP-SAT week placement**.
It is NOT "hand everything to the solver".

| Phase | Who decides | What is decided |
|-------|-------------|-----------------|
| Group formation (heuristic) | `form_groups()` | For each lab group: its **day**, **time block**, **room**, and its **student members**. Respects free/busy slots, min/max group size, shared groups (Fisica/Quimica), program homogeneity for first year, professor-busy slots, and a soft Friday anti-bottleneck penalty. |
| Week placement (CP-SAT) | `solve()` | The only free variable is **which academic week** each session runs in. The solver spreads sessions, avoids clashes (C1/C4), enforces chronological order (C5), and minimizes soft spacing penalties. |
| Professor assignment (post-hoc) | `lab_professor_assignment.py` | After a schedule exists, the responsible professor per group is derived from the official P credits (1 P credit = 5 sessions), proportionally. Persisted into the schedule (`professor` column). |

Consequence to keep in mind: **the CP-SAT model does not choose the slot or the
room** — those are fixed upstream by the heuristic. So an "infeasible" CP-SAT
result is almost always a **week-capacity** problem (too many sessions forced
into the same room/slot across too few available weeks), not a slot-assignment
problem. This is exactly what the infeasibility diagnostic reports.

---

## 3. Mapping to the whiteboard architecture (`architecture.jpg`)

The whiteboard sketch defines the intended data flow. The code follows it:

| Whiteboard node | Code responsibility | Notes |
|-----------------|---------------------|-------|
| Students -> enrollment | `identify_students()` | Builds subject -> student sets from the master schedule. |
| Course schedule -> Student schedule | `build_individual_timetables()` | Per-student busy/free slots derived from their course timetable. |
| Student schedule -> busy / free slots | `student_busy`, `student_subject_slots` | 30 possible slots (5 days x 6 blocks); occupied slots removed. |
| Professors -> teaching assignments (normal class) | `prepare_professor_constraints()`, `build_professor_busy()` | Professor busy slots from their normal teaching load. |
| Course schedule -> Professor schedule -> busy / free | `build_subject_professor_busy()` | A group of a subject cannot be created on a slot where a professor of that subject is busy (soft-relaxable). |
| Professor lab teaching assignment: which labs? how many credits / groups? | `lab_professor_assignment.py`, `professor_credits.py` | Which labs, how many P credits, how many groups per professor — derived from the official "Asignacion docente". |
| Coincidencias / Gaps | soft objective terms in `solve()` + `reliability_metrics.py` | Spacing/gap deviation minimized; balance and health scored post-hoc. |

The whiteboard's "busy/free" duality is the backbone: **every actor (student,
professor, room) has a busy set, and the complement is the free set** the engine
schedules into.

---

## 4. End-to-end pipeline map

Entry point: `pipeline.py :: main()` -> `run_pipeline(df)`. Each stage reads and
writes explicit artifacts, so any stage can be inspected or replaced.

```
                         data_clean/master_schedule.csv
                                     |
                                     v
  [1] load_and_prepare(df)                      normalize columns, types
                                     |
                                     v
  [2] identify_students(df)                      subject -> {student ids}
                                     |
                                     v
  [3] build_individual_timetables(df, ...)       student_busy, student_subject_slots
                                     |
                                     v
  [4] prepare_professor_constraints(df)          subject_professor_busy,
      build_student_program_lookup(df)           subject_block_penalty,
                                                  professors_of_subject
                                     |
                                     v
  =============== HEURISTIC ===============
  [5] form_groups(...)                           all_groups: each group has a
                                                  FIXED (day, block, room) and its
                                                  student members
                                     |
                                     v
  [6] run_data_quality_checks(...)  (data_quality.py, non-blocking)
      audit_teacher_max_days(...)
      verify_availability_constraints(...)       config/availability_verification.json
                                     |
                                     v
  =============== CP-SAT SOLVER ===============
  [7] solve(all_groups)                          per semester:
        - week_vars: IntVar per session (domain = valid weeks)
        - C1: no two sessions of same SUBJECT in same (week, day, block)
        - C4: no two sessions in same ROOM in same (week, day, block)
        - C4-reserved: soft penalty for externally reserved room-slots
        - C5: sessions of a group are chronologically ordered
        - soft objective: first-session anchor, last-session anchor,
          even gap spacing, parity alternation, Friday cap
        - status -> record_solver_run() -> reports/solver_stats.json
        - if INFEASIBLE: diagnose_infeasibility() + automatic recovery
          (drop over-saturated groups, re-solve)
                                     |
                                     v
      results_df (semester, subject, grupo, session, week, day, time_block, room)
                                     |
                                     v
  =============== POST-PROCESSING ===============
  [8] lab_professor_assignment.assign_professors_to_schedule_df(results_df)
        -> results_df['professor']   (P0.1: professor persisted in schedule)
                                     |
                                     v
  [9] kpi_report.generate_kpi_report(...)        reports/kpi_report.{json,txt}
                                     |
                                     v
  [10] generate_outputs(...)                     outputs/optimization/*.csv + .xlsx
       analyze(results_df)                        (Grupo de practicas, Vista profesor,
                                                   Teacher View, quality sheets)
                                     |
                                     v
  [11] run_daniel_format_generation()            Distribucion_Practicas_*.xlsx
       create_auto_snapshot()                     versions/<name>/
```

### Stage responsibility table

| # | Stage | Function (file) | Reads | Writes |
|---|-------|-----------------|-------|--------|
| 1 | Load & prepare | `load_and_prepare` (pipeline.py) | master_schedule.csv | in-memory df |
| 2 | Identify students | `identify_students` | df | subject_students |
| 3 | Student timetables | `build_individual_timetables` | df, subject_students | student_busy, student_subject_slots |
| 4 | Professor constraints | `prepare_professor_constraints`, `build_professor_busy` | df, Asignacion | subject_professor_busy, professors_of_subject |
| 5 | Group formation (heuristic) | `form_groups` | all of the above | all_groups (day/block/room fixed) |
| 6 | Data quality / audits | `data_quality.py`, `audit_teacher_max_days`, `verify_availability_constraints` | df, all_groups | data_quality_report.*, availability_verification.json |
| 7 | CP-SAT solve | `solve` | all_groups | results_df, solver_stats.json, infeasibility_S*.txt |
| 8 | Professor assignment | `lab_professor_assignment.py` | results_df, Asignacion | results_df['professor'] |
| 9 | KPI report | `kpi_report.py` | results_df, all_groups, solver_runs | kpi_report.{json,txt} |
| 10 | Excel/CSV export | `generate_outputs`, `excel_generator_core.py` | results_df | outputs/optimization/*.{csv,xlsx} |
| 11 | Daniel format + snapshot | `run_daniel_format_generation`, `create_auto_snapshot` | outputs | Distribucion_Practicas_*.xlsx, versions/ |

---

## 5. The CP-SAT model in detail

Built inside `solve()`, one model per semester.

### Variables
- `week_vars[session_id]`: integer variable, domain = the valid weeks for that
  session (min_week..max_week minus holidays for that weekday).

### Hard constraints
- **C1** (subject clash): for sessions of the same subject on the same
  (day, block), all weeks must differ.
- **C4** (room clash): for sessions in the same room on the same (day, block),
  all weeks must differ.
- **C5** (chronological order): within a group, session k+1 runs strictly after
  session k.

### Soft constraints (objective, minimized)
- **C4-reserved**: heavy penalty when a session lands on an externally reserved
  room-slot (allowed, but strongly discouraged).
- **First-session anchor**: penalize starting late.
- **Last-session anchor**: penalize finishing early.
- **Gap spacing**: penalize deviation from the ideal even spacing between sessions.
- **Parity alternation**: alternate parallel groups across even/odd weeks.
- **Friday cap**: constant + escalating penalty above a soft session cap on
  Fridays (anti-bottleneck), never a hard ban.

> **Phase 2 note — configurable weights.** The first-anchor, last-anchor,
> spacing and parity penalties now read their weights and on/off state from
> `config/solver_constraints.yaml` via `solver_config.py`. When the file is
> absent or invalid, the historical defaults (100 / 100 / 200 / 50) are applied,
> so behaviour is unchanged. See section 10.

### Warm start
`add_week_hints()` injects an evenly-spread week assignment as a solver hint to
speed convergence.

---

## 6. Solver status semantics (why OPTIMAL / FEASIBLE / INFEASIBLE)

`record_solver_run()` writes one entry per solve into `reports/solver_stats.json`
with: status, objective, best_bound, gap, wall_time_s, n_sessions, n_hints,
recovered.

| Status | Meaning | Typical cause | Recommended reaction |
|--------|---------|---------------|----------------------|
| OPTIMAL | Proven best solution; gap ≈ 0 | Model well constrained, time sufficient | Ship it. |
| FEASIBLE | A valid solution found, but not proven optimal (gap > 0) | Time limit hit before proof, or hard combinatorics | Usually fine to ship; increase time limit or relative gap to tighten if desired. |
| INFEASIBLE | No valid week assignment exists | Physical capacity: too many sessions forced into the same room/slot across too few available weeks | Read `infeasibility_S*.txt` bottlenecks; open a slot/room, widen the [min_week, max_week] window, or reduce parallel groups. Automatic recovery drops the over-saturated groups and re-solves. |
| UNKNOWN | Solver stopped without conclusion | Time limit with no solution | Increase time limit; inspect bottlenecks. |

### Automatic recovery
When a semester is INFEASIBLE, `solve()` does not give up:
1. `diagnose_infeasibility()` scans room-slot and subject-slot groups for
   over-saturation (needed sessions > available weeks) and writes a readable
   report.
2. The over-saturated groups are dropped by priority (overflow > recovered >
   alt_room), the model is rebuilt on the remaining sessions and re-solved.
3. Dropped groups are flagged `_solver_dropped` and surfaced downstream; the run
   is recorded with `recovered=True`.

This is the "signal, do not hide" contract: an infeasibility is always explained
and, when possible, recovered — never silently swallowed.

### Unplaced students
`diagnose_unplaced_students()` explains, per enrolled-but-unplaced student, why:
either a total timetable conflict (no common slot with any group), saturated
compatible slots (room/group capacity reached), or a cohort/program constraint.
Written to `reports/unplaced_students.json`.

---

## 7. Module map (current monolith)

| File | Role |
|------|------|
| `pipeline.py` | Orchestrator: ingestion, heuristic, CP-SAT, recovery, exports. Core of the engine. |
| `form_groups` (in pipeline.py) | Heuristic group formation. |
| `solve` (in pipeline.py) | CP-SAT week-placement model + recovery. |
| `lab_professor_assignment.py` | Per-group responsible professor from P credits. |
| `professor_credits.py` | P/T credit parsing and budgets from Asignacion docente. |
| `lab_constants.py` | Single source of truth for `CREDIT_TO_SESSIONS = 5`. |
| `data_quality.py` | Non-blocking data-integrity checks (join reconciliation, anti-leak). |
| `kpi_report.py` | Objective KPIs (placement, balance, rooms, solver) per run. |
| `validation_credits.py` | Credit rule validation. |
| `reliability_metrics.py` | 0-100 health score and reliability signals. |
| `monitoring.py` | Streamlit "control tower" page: pure collectors + render. |
| `excel_generator_core.py` | Excel workbook generation (Grupo de practicas, Vista profesor, Teacher View, quality sheets). |
| `app.py` | Streamlit application shell and page routing. |

### Data artifacts

Inputs (read):
- `data_clean/master_schedule.csv` — the consolidated source of truth.
- Asignacion docente file — official professor credits.
- Aulario / Alumnos sources — rooms and students.
- `config/user_config.json` — user overrides and teacher rules.

Outputs (written):
- `outputs/optimization/optimized_schedule_v5.{csv,xlsx}` — the schedule.
- `outputs/optimization/group_composition.csv` — groups and members.
- `reports/solver_stats.json` — one entry per solve.
- `reports/unplaced_students.json` — unplaced diagnostics.
- `reports/infeasibility_S*.txt` — infeasibility bottlenecks.
- `reports/kpi_report.{json,txt}`, `reports/data_quality_report.*` — quality.
- `versions/<name>/` — auto snapshots.

---

## 8. Architecture assessment and scaling roadmap

The current design is a **modular monolith**: a single Streamlit app plus a
procedural pipeline, with the business logic already split into focused modules
(`professor_credits`, `lab_professor_assignment`, `data_quality`, `kpi_report`,
`reliability_metrics`, `monitoring`). This is the right choice for the current
scale and the desktop `.exe` distribution: simple to build, ship and debug.

To scale toward an enterprise / multi-tenant engine (exam scheduling, an AI
university agent, other institutions), the recommended evolution is incremental,
never a rewrite (consistent with `FUNCTIONAL_COMPARISON.md`):

1. **Isolate the solver core** behind a stable, framework-free interface:
   `build_model(problem) -> model`, `solve(model) -> solution`,
   `diagnose(model) -> report`. This is the seam that makes every future use
   case (labs, exams) a different `problem` input to the same core.
2. **Introduce a problem schema** (a typed description of actors, slots,
   constraints, objectives) so new domains are configuration, not new code.
   This is the foundation for the "configurable soft/hard constraints" request.
3. **Expose an API layer** (FastAPI) over the core, then an **MCP server** that
   maps tools to the same endpoints, for the AI-agent integration.
4. **Add a job queue** (e.g. RQ/Celery) for long solves so the API stays
   responsive; persist runs in a real store rather than loose JSON files.
5. **Package multi-platform** (Docker image + hosted web app) so macOS/Linux
   users are not blocked by the Windows-only `.exe`.

Only when the problem schema and multiple domains genuinely exist does a fuller
layered ("clean") architecture pay for itself. Until then, the modular monolith
plus a cleanly isolated solver core is the pragmatic, maintainable path.

---

## 9. Observability contract

Everything the engine does is meant to be inspectable, not hidden:
- Every solve is journaled (`solver_stats.json`), with status, gap and time.
- Every infeasibility is explained (`infeasibility_S*.txt`) and, when possible,
  recovered.
- Every unplaced student has a verdict (`unplaced_students.json`).
- Data quality, KPIs and a health score are produced on every run.
- The `monitoring.py` control-tower page aggregates all of the above into one
  read-only view, including a Solver Diagnostics panel that translates raw
  solver status into a plain-language "why this result and what to do next".

This observability is the QA backbone that lets the same engine be trusted in
production and extended to new use cases.



---

## 10. Phase 2 components (configurable constraints + infeasibility simulation)

Phase 2 adds two additive, read-only-by-default capabilities. No validated
solver logic or data-processing stage is modified; the solver only reads weights
that default to the historical values.

### 10.1 Configurable soft constraints

| Piece | File | Role |
|-------|------|------|
| Schema + loader | `solver_config.py` | Validated load/save of soft-constraint weights and on/off flags; 3 presets (Strict / Balanced / Relaxed); defaults reproduce the historical weights. |
| Config file | `config/solver_constraints.yaml` | Human-editable weights, flags and preset reference. Missing/invalid -> Balanced defaults. |
| Solver hook | `pipeline.solve()` | Loads config once, applies effective weights to the objective terms, and appends a `constraint_config` summary to each `solver_stats.json` entry. A disabled constraint contributes weight 0, i.e. the term is skipped. |
| UI | `ui_solver_constraints.py` (tab "Contraintes du solveur" of the single Configuration page in `app.py`) | Profile selector, per-constraint toggles + weight sliders, live preview, extreme-config warnings, save/reset with confirmation. |

The four tunable soft constraints are `semester_anchor_first`,
`semester_anchor_last`, `spacing`, `parity`. Hard constraints (C1/C4/C5) and the
reserved-slot penalty are intentionally NOT exposed (they are correctness, not
preference).

### 10.2 Infeasibility simulation (What-If)

| Piece | File | Role |
|-------|------|------|
| Engine | `simulation_engine.py` | Pure, side-effect-free capacity/bottleneck model plus an optional real CP-SAT feasibility dry-run. Never writes to `reports/`/`outputs/`. |
| UI | `pages/4_Simulateur_Infaisabilite.py` | At-a-glance summary of the latest run (feasibility, bottlenecks, unplaced students, data freshness), then: (1) automatic suggestions (auto-run on infeasibility), (2) manual group exclusion, (3) extra room/time-slot capacity. |

Engine entry points:
- `simulate_without_groups(sessions, group_ids)` — recompute bottlenecks with
  groups removed; reports overflow reduction and affected students.
- `simulate_with_extra_capacity(sessions, extra_slots)` — recompute with extra
  weeks added to given `(resource, day, block)` slots.
- `suggest_actions(sessions)` — rank groups to drop / resources to add.
- `dry_run_feasibility(sessions)` — build C1/C4/C5 and solve for feasibility only.
- Read-only loaders parse `reports/unplaced_students.json`,
  `reports/solver_stats.json` and `reports/infeasibility_S*.txt`.

Every simulation returns a `before` / `after` / `diff` structure so the UI can
show the metric delta and whether a scenario would become feasible.

See `PHASE2_FEATURES.md` for usage details.



## 11. Phase 3 components (enhanced Excel exports)

Phase 3 adds a richer, analysis-oriented Excel export layer. It is **purely
additive**: the validated Daniel-format exporters (`excel_export.py` +
`excel_generator_core.py`) are never modified, and the `standard` format simply
delegates to them, so existing deliverables stay byte-for-byte identical.

### 11.1 Module map

| Piece | File | Role |
|-------|------|------|
| Enhanced engine | `excel_export_enhanced.py` | Builds colour-coded group sheets, a legend, and five analysis sheets (Room Utilization, Professor Workload, Student Placement, Time Slot Analysis, Quality Metrics). Owns all styling helpers (branded headers, alternating rows, conditional formatting, charts, comments, freeze panes, auto-filters, data validation, named ranges). |
| Format & template manager | `export_manager.py` | Maps a `format_type` (`standard` / `enhanced` / `summary` / `detailed`) to an `ExportOptions` profile; loads `config/export_preferences.yaml`; and implements the template engine (discover / validate / render `{{TOKEN}}` placeholders). |
| Preferences | `config/export_preferences.yaml` | Default format, default colour scheme, per-format flag overrides, templates directory. Missing/invalid -> built-in defaults. |
| Templates | `templates/*.xlsx` | Branded workbooks with `{{TOKEN}}` placeholders. `loyola_schedule_template.xlsx` ships by default; `templates/build_loyola_template.py` regenerates it deterministically. |
| UI | `ui_advanced_exports.py` (section "Exports avances" of the Export page in `app.py`) | Perimeter/format/colour-scheme selectors, per-sheet and per-formatting checkboxes, data preview, generate + download, and a template renderer — applied directly where the Excel files are generated. |

### 11.2 Formats

| Format | Sheets | Notable |
|--------|--------|---------|
| `standard` | (delegates to `excel_export`) | Daniel-format workbooks, unchanged. |
| `summary` | Overview, Groups, Legend, Student Placement, Quality Metrics | Lightweight overview. |
| `enhanced` | All sheets | Full analysis with charts, comments, validation, named ranges. |
| `detailed` | All sheets | Same as enhanced but sheets are protected (filters stay usable). |

### 11.3 Group sizing thresholds (status semantics)

Mirror `pipeline.py`: `MIN_GROUP_SIZE = 7`, `PREFERRED_GROUP_SIZE = 12`,
`MAX_GROUP_SIZE = 15`. A group is **optimal** when `7 <= size <= 15`,
**under-utilized** below 7, **over-subscribed** above 15. Conditional
formatting and the status column both apply this rule.

### 11.4 Accessibility

Status colours use a colour-blind-safe (Okabe-Ito derived) palette — optimal
`#009E73` (bluish green), under-utilized `#E69F00` (orange), over-subscribed
`#D55E00` (vermillion). Status is additionally encoded with a text label and a
fill *pattern*, so meaning never relies on colour alone. Per-group colours use
the qualitative Okabe-Ito set, extended deterministically via HSL for large
group counts so a group's colour is stable across every sheet.

### 11.5 Public API

- `export_manager.export_with_format(format_type, *, semester=None, out_path=None, color_scheme=None, overrides=None)`
- `export_manager.render_template(name, context, *, out_path=None)`
- `excel_export_enhanced.build_enhanced_workbook(schedule_df, groups_df, *, kpi, solver_stats, options, color_scheme, semester)`
- `excel_export_enhanced.export_enhanced(semester=None, *, out_path=None, options=None, color_scheme='loyola')`

Room capacity for cell comments is a documented proxy (max students ever
scheduled in a room) because the pipeline outputs carry no explicit capacity.

See `PHASE3_EXCEL_FEATURES.md` for usage details.



---

## 12. Multi-Department Vision — Scheduling Platform Abstraction

**Status:** Strategic proposal (Phase A) for final presentation. Proof-of-concept architecture demonstrating how the lab scheduling engine can generalize to other university planning domains.

### 12.1 Strategic Motivation

The current LabScheduling application solves a **specific** problem: assigning lab practice groups to time/room slots. However, the underlying constraint satisfaction engine (CP-SAT + conflict detection + room capacity + validation) implements a **general pattern**:

> *Given entities (groups/exams/sessions), time slots (day × hour × room), and conflict rules, find an assignment that satisfies all hard constraints and optimizes soft preferences.*

This same pattern applies to:
- **Final exams** (one exam per subject, 2-week period, no student has >2 exams/day)
- **Lecture hall assignment** (large courses need specific rooms, avoid professor conflicts)
- **Office hours / consultations** (faculty availability, student booking)
- **Other institutions** (different credit systems, room types, constraints)

**Value proposition:**
- For Loyola: Unified scheduling platform reducing tool fragmentation
- For other universities: Adaptable to their academic structure
- For final presentation: Demonstrates systems thinking and architectural maturity

### 12.2 Four-Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Layer 4: Unified UI                                    │
│  ├─ Multi-Profile page (select Lab/Exam/Lecture/...)   │
│  ├─ Dynamic config UI (adapts to selected profile)     │
│  └─ Profile-specific exports                            │
└─────────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Domain Adapters                               │
│  ├─ pipeline.py (lab practice adapter)                  │
│  ├─ exam_scheduler.py (future exam adapter)             │
│  └─ Backward compatibility wrappers                     │
└─────────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Profile System                                │
│  ├─ config/scheduling_profiles/*.yaml                   │
│  │   ├─ lab_practice.yaml (current production)          │
│  │   ├─ final_exam.yaml (hypothetical demo)            │
│  │   └─ Custom profiles (institution-specific)         │
│  └─ SchedulingProfile dataclass                         │
└─────────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Generic Scheduling Core                       │
│  ├─ scheduling_core.py                                  │
│  │   ├─ solve_generic() — domain-agnostic CP-SAT       │
│  │   ├─ Conflict detection (student/prof/room)         │
│  │   └─ Constraint builder from profile rules          │
│  └─ Already-generic components:                         │
│      ├─ schedule_validation.py (structure-agnostic)     │
│      ├─ excel_export*.py (DataFrame → workbook)         │
│      └─ solver_config.py (soft constraint tuning)       │
└─────────────────────────────────────────────────────────┘
```

### 12.3 What is Generic vs. Domain-Specific

| Aspect | Lab Practice (Current) | Final Exam (Hypothetical) | Abstraction |
|--------|------------------------|---------------------------|-------------|
| **Entity** | Practice group (students in lab component) | Exam session (all students taking final) | `SchedulableEntity` with ID, students, duration |
| **Repetitions** | 5 sessions per group (1 P = 5 practices) | 1 exam per subject | `sessions_per_entity` (1 or N) |
| **Time window** | 15-week semester | 2-week exam period | `scheduling_weeks` (min, max) |
| **Room type** | Lab rooms (Ciencias Exp., Robótica) | Large lecture halls (Aula Magna) | `room_filter_type` + capacity |
| **Spacing** | Prefer 2-week gaps between practices | No spacing (1 exam only) | Optional soft constraint |
| **Student conflict** | No 2 labs simultaneously | No 2 exams simultaneously | **Generic** (C1) |
| **Room conflict** | 1 room holds 1 group | 1 room can hold multiple small exams (if capacity allows) | **Generic** (C4) + `capacity_mode` |
| **Professor role** | 1 dedicated prof per group (fixed) | Any prof can proctor (flexible) | `instructor_fixed` flag |
| **Credit system** | 1 P credit = 5 sessions | 1 exam slot (no credits) | `credit_to_sessions_multiplier` |

**Key insight:** Student conflict, room capacity, and instructor conflict are **already generic** in the current codebase. Only the *credit system*, *repetition count*, and *room assignment rules* are lab-specific.

### 12.4 Profile System

**Module:** `scheduling_core.py` (new, Phase A stub)  
**Config:** `config/scheduling_profiles/*.yaml`

A **SchedulingProfile** is a YAML file defining:
```yaml
domain: lab_practice | final_exam | lecture_hall | ...
entity_label: Group | Exam | Course | ...
sessions_per_entity: 5  # How many times entity is scheduled
scheduling_weeks: {min: 1, max: 15}
allow_repetitions: true | false

hard_constraints:
  - student_conflict
  - room_capacity
  - max_exams_per_day_per_student  # Domain-specific constraint

soft_constraints:
  spacing: 200
  fair_distribution: 100

room_filter: {type: lab_rooms, min_capacity: 40}
capacity_mode: per_group | aggregate
instructor_fixed: true | false
output_sheets: [...]  # Which Excel sheets to generate
```

**Usage:**
```python
from scheduling_core import SchedulingProfile, solve_generic

# Load profile
profile = SchedulingProfile.from_yaml("config/scheduling_profiles/lab_practice.yaml")

# Solve
schedule = solve_generic(entities, time_slots, busy_slots, profile, solver_config)
```

### 12.5 Implementation Roadmap

**Phase A (current, for demo):**
- ✅ Architecture design document (`MULTI_DEPARTMENT_ABSTRACTION.md`)
- ✅ Profile system with 2 examples (`lab_practice.yaml`, `final_exam.yaml`)
- ✅ Stub `scheduling_core.py` (delegates to `pipeline.py` for lab profile)
- ✅ Documentation updates (this section)
- 📋 Visual assets (architecture diagram, comparison slides)

**Phase B (post-presentation, production):**
- Refactor `pipeline.py` to extract generic CP-SAT logic into `scheduling_core.solve_generic()`
- Implement exam-specific constraints (`max_exams_per_day_per_student`, `spacing_student_exams`)
- Build exam data loaders and adapters
- Full test suite for multi-profile system
- Multi-Profile UI page (`pages/7_Multi_Profil.py`)

**Phase C (future platform features):**
- Visual profile editor (YAML → web form)
- Constraint marketplace (library of pre-built constraints)
- Multi-semester planning (Labs S1 + Exams S1 + Labs S2 + Exams S2 in one pass)
- External API for third-party integrations

### 12.6 Strategic Use Cases

**Use Case 1: Final Exams (January / June)**
- **Pain point:** Manual exam scheduling → student conflicts, unfair distribution (3 exams in 1 day)
- **Solution:** Load `final_exam.yaml`, run solver with same student enrollment data
- **Output:** `Exam_Schedule_S1.xlsx` with no conflicts, max 2 exams/day/student
- **Impact:** Saves ~40 hours per exam period (2× per year)

**Use Case 2: Other Universities**
- **Scenario:** Universidad de Sevilla has different credit system (1 credit = 3 sessions, not 5)
- **Solution:** Create `config/scheduling_profiles/sevilla_lab.yaml` with their rules
- **Impact:** Tool becomes **multi-tenant** and institutionally agnostic

**Use Case 3: Multiple Departments at Loyola**
- Engineering labs (current)
- Business exams (new)
- Law lecture halls (future)
- All using the same platform with different profiles

### 12.7 Backward Compatibility

**Critical:** The lab scheduling engine (`pipeline.py`, `excel_export.py`, all validated sheets) continues to work unchanged. The abstraction is **purely additive**:

- `pipeline.py` becomes a thin wrapper around `scheduling_core.solve_generic()` for the lab profile
- Existing CLI/UI workflows continue to call `pipeline.solve()` (which now delegates internally)
- No breaking changes to data formats, outputs, or APIs
- Profile system is opt-in (discovered via `list_available_profiles()`)

### 12.8 For Final Presentation

**Narrative:**
> "We started by solving lab scheduling for Loyola Engineering. But we quickly realized the underlying constraint satisfaction pattern is **universal**. The same engine that schedules lab practices can schedule final exams, lecture halls, office hours — or adapt to a different university's rules entirely. We've built not just a tool, but a **platform** for university-wide planning."

**Demo:** Show side-by-side:
1. Current Lab solver → `Distribucion_Practicas_AUTO.xlsx`
2. Hypothetical Exam solver (mock data) → `Exam_Schedule_S1.xlsx`
3. Same `scheduling_core` engine, different profiles

**Impact statement:**
- **For Loyola:** Unified scheduling platform (labs + exams + lectures) from 1 codebase
- **For other institutions:** Adaptable via YAML config (no code changes)
- **For presentation jury:** Demonstrates systems thinking beyond a single use case

See `docs/MULTI_DEPARTMENT_ABSTRACTION.md` for full technical design.
