# Clean Architecture Integration Guide

This document explains how the `clean_architecture/` module fits inside the
existing **LabScheduling** repository, how the two codebases coexist without
interfering, and how to migrate progressively.

---

## 1. Why a dedicated subfolder?

The repository historically contains a working **monolithic** application
(`app.py` ~286 KB, `pipeline.py` ~239 KB, `excel_generator_core.py`, ...). It is
in active use and must keep working.

The `clean_architecture/` folder is a **self-contained, non-destructive**
re-implementation of the same domain following Clean Architecture. It was added
in coexistence mode:

- The legacy code at the repository root is **untouched and fully functional**.
- The new module lives entirely under `clean_architecture/` with its own
  `requirements.txt`, `config/`, `tests/`, `Dockerfile`, and docs.
- Nothing in the legacy pipeline imports from `clean_architecture/` and vice
  versa, so the two can evolve independently.

This lets the team review, test and adopt the new architecture gradually before
deciding whether to retire the monolith.

---

## 2. Layout

```
LabScheduling/                     <- repository root (legacy, unchanged)
├── app.py                         #   legacy Streamlit monolith
├── pipeline.py                    #   legacy solver + ETL
├── excel_generator_core.py        #   legacy Excel output
├── data/  data_clean/  assets/    #   shared real data and branding
├── tests/                         #   legacy tests
│
└── clean_architecture/            <- NEW self-contained module
    ├── domain/                    #   entities, value objects, pure rules
    ├── application/               #   services + use cases
    ├── infrastructure/            #   CP-SAT solver, Excel I/O, config, security
    ├── presentation/              #   Streamlit UI, monitoring, sandbox
    ├── config/config.yaml         #   externalised configuration (no hardcoding)
    ├── tests/                     #   46 unit/integration tests
    ├── ci/                        #   CI workflow reference files + setup guide
    ├── Dockerfile / docker-compose.yml
    └── README.md / DEPLOYMENT.md / SECURITY.md / GETTING_STARTED.md
```

---

## 3. Legacy module -> Clean Architecture mapping

| Legacy file (root)            | Clean Architecture equivalent                                   |
|-------------------------------|-----------------------------------------------------------------|
| `pipeline.py` (solver part)   | `infrastructure/solver/solver_engine.py` + `constraint_manager.py` |
| `pipeline.py` (LAB_CONFIG)    | `config/config.yaml` + `infrastructure/config/config_loader.py` |
| `professor_credits.py`        | `application/services/credit_system.py` + `domain/rules.py`     |
| `validation_credits.py`       | `application/services/credit_system.py` (`CreditValidator`)      |
| `lab_professor_assignment.py` | `application/services/scheduler_service.py` (`allocate_professors`) |
| `excel_generator_core.py`     | `infrastructure/excel/excel_generator.py`                       |
| `excel_export.py` / readers   | `infrastructure/excel/excel_reader.py`                          |
| `data_quality.py`             | `application/services/conflict_detector.py`                     |
| `kpi_report.py`               | `application/services/monitoring_service.py` + `validation_report.py` |
| `app.py`                      | `presentation/app.py` + `presentation/pages/*`                  |

---

## 4. Key business rule preserved

The credit rule is enforced in one place, `domain/rules.py`:

> **1 Practice (P) credit = 5 lab sessions.** Theory (T) credits are ignored for
> lab scheduling.

`infrastructure/excel/excel_reader.py` reads only the practice part of each
assignment (splitting `TP` rows proportionally), and
`application/services/credit_system.py` audits expected vs. assigned sessions.

---

## 5. Running the new module

All commands run **from inside `clean_architecture/`**:

```bash
cd clean_architecture

# 1. Environment
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. Tests (46 should pass)
pytest -v

# 3. Lint
ruff check .

# 4. App (http://localhost:8501)
streamlit run presentation/app.py
```

Docker:

```bash
cd clean_architecture
docker compose up -d --build
```

> This localhost refers to the machine where you run the command, not a remote
> server.

---

## 6. Using the real data files

The new module runs out of the box in **demo/simulation mode**, building inputs
from `config/config.yaml` (no large files needed).

For **real ingestion**, place the source workbook where the reader/tests can
find it. The integration test searches, in order:

1. `LABSCHEDULING_ASSIGNMENT_FILE` environment variable
2. `clean_architecture/data/Asignacion_2025-2026_v5.xlsx`
3. repository root `Asignacion_2025-2026_v5.xlsx`

```bash
# Example: point the reader at a file anywhere on disk
export LABSCHEDULING_ASSIGNMENT_FILE=/path/to/Asignacion_2025-2026_v5.xlsx
pytest -v tests/test_integration_real_file.py
```

The `Asignacion_*.xlsx` files remain git-ignored (sensitive source data); the
shared `data/` and `data_clean/` folders at the repository root are reused.

---

## 7. CI/CD

Two reference workflows are provided in `ci/` (`tests.yml`, `lint.yml`), scoped
to `clean_architecture/**` so they never collide with the legacy pipeline.
Activation takes two minutes - see [`ci/CI_SETUP.md`](ci/CI_SETUP.md).

---

## 8. Suggested migration path

1. **Review** this module and run its tests/app locally.
2. **Activate CI** (`ci/CI_SETUP.md`) so every change is validated.
3. **Validate** the generated Excel against the legacy output on real data.
4. Once confident, **switch** the default entry point to
   `clean_architecture/presentation/app.py` and move the legacy files into a
   `legacy/` folder (a later, separate PR).
