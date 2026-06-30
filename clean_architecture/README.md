# University Lab Scheduler

AI-powered laboratory scheduling system for engineering schools using CP-SAT
optimization.

[![Tests](https://img.shields.io/badge/tests-46%20passing-brightgreen.svg)](ci/CI_SETUP.md)
[![Lint](https://img.shields.io/badge/ruff-clean-brightgreen.svg)](ci/CI_SETUP.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

This project automates the scheduling of laboratory (practice) sessions for an
engineering school. It builds homogeneous lab groups, allocates teachers in
proportion to their official practice credits, and uses a Google OR-Tools
CP-SAT constraint solver to decide the optimal week for every session while
respecting rooms, time windows, holidays and reserved slots. It is implemented
following Clean Architecture principles so the domain logic stays independent
of the solver, the spreadsheet I/O and the user interface.

The reference dataset comes from Universidad Loyola Sevilla, so domain data
(subject names, day names, room names and program codes) is kept in Spanish on
purpose. The codebase, comments, documentation and configuration are in English.

---

## Architecture

```
lab_scheduler/
├── domain/                      # Business core - NO external dependencies
│   ├── entities/                #   Professor, Subject, Group, LabSession, Constraint
│   ├── value_objects.py         #   TimeSlot, WeekWindow, Credits, TimeBlock, Period
│   └── rules.py                 #   Pure rules (1 P credit = 5 sessions, Friday penalty...)
│
├── application/                 # Use cases and orchestration services
│   ├── services/
│   │   ├── credit_system.py     #   CreditSystem + CreditValidator (gap audit)
│   │   ├── conflict_detector.py #   ConflictDetector (C1/C4/C5/student)
│   │   └── scheduler_service.py #   SchedulerService (solver + teacher allocation)
│   └── use_cases/
│       └── run_scheduling.py    #   RunSchedulingUseCase (entry point use case)
│
├── infrastructure/              # Concrete implementations (I/O, solver)
│   ├── config/config_loader.py  #   ConfigLoader: config.yaml -> typed objects
│   ├── solver/
│   │   ├── constraint_manager.py#   ConstraintManager: builds CP-SAT constraints
│   │   └── solver_engine.py     #   CPSATSolver: OR-Tools engine (decides the week)
│   └── excel/
│       ├── excel_reader.py      #   ExcelReader: credits and schedules
│       └── excel_generator.py   #   ExcelGenerator: output workbooks
│
├── presentation/                # Streamlit UI (display only)
│   ├── app.py                   #   Entry point (wizard)
│   ├── pages/                   #   config_page, results_page, monitoring, sandbox
│   └── components/              #   reusable UI components
│
├── config/config.yaml           # All externalized configuration
├── tests/                       # Unit and integration tests (pytest)
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Development and test dependencies
└── pyproject.toml               # Packaging and tooling configuration
```

### Dependency rule

Dependencies point **inward**: `presentation -> application -> domain`.
The infrastructure layer implements ports defined by the application layer
(for example `SchedulingSolver`), so the domain and application layers never
depend on OR-Tools, openpyxl or Streamlit.

```
        +--------------+
        | presentation |  Streamlit
        +------+-------+
               v
        +--------------+
        | application  |  services + use cases
        +------+-------+
               v
        +--------------+        +----------------+
        |   domain     |<-------| infrastructure |  (implements the ports)
        +--------------+        +----------------+
```

---

## Externalized configuration (`config/config.yaml`)

All scheduling parameters (subjects, sessions, rooms, time windows, holidays,
Friday cap, objective weights, group sizes, reserved slots) live in
`config/config.yaml`. Changing the schedule requires **no code change**.

```yaml
credit_system:
  sessions_per_credit: 5          # core business rule

subjects:
  S1_Física:
    curso_num: 1
    num_sessions: 5
    min_week: 4
    max_week: 14
    lab_rooms: ["Ciencias Experimentales I", "Ciencias Experimentales II"]
    ...
```

The `ConfigLoader` parses this file and returns typed objects (`AppSettings`,
`Subject`). It is the **only** component that knows the YAML format.

---

## Credit system (core business rule)

The scheduler only counts **practice (P) credits**. Theory (T) credits are
ignored, and combined theory+practice (TP) entries are split to keep only the
practice portion. The conversion rule is:

```
1 practice (P) credit = 5 laboratory sessions
```

This rule is implemented in `domain/rules.py` and configured by
`credit_system.sessions_per_credit` in `config/config.yaml`. The
`infrastructure/excel/excel_reader.py` module enforces the policy when reading
the teaching-assignment spreadsheet:

- type `P` (pure practice): all credits are used,
- type `TP` (theory + practice): only the practice portion is kept, using the
  ratio `practice / (theory + practice)`,
- type `T` (pure theory) and any other type: skipped.

The behavior is covered by tests, including
`test_read_assignments_skips_theory`, which asserts that pure-theory subjects
never contribute any P credits.

---

## Critical components

| Module | Role |
|--------|------|
| `domain/rules.py` | Rule `P credits x 5 = sessions`; pure and fully tested |
| `credit_system.py` | `CreditValidator` detects credit/session gaps |
| `scheduler_service.py` | Teacher-to-group allocation proportional to P credits |
| `constraint_manager.py` | CP-SAT constraints (C1/C4/C5/parity/reservations) |
| `solver_engine.py` | CP-SAT engine (seed=42, gap=2%, multi-criteria objective) |
| `conflict_detector.py` | Independent post-solve validation of the schedule |

### Teacher allocation by credits

Teacher-to-group allocation is the main source of load imbalance in manual
schedules. `SchedulerService.allocate_professors` assigns each group to the
teacher with the largest remaining **quota deficit** (quota = P credits x
`sessions_per_credit`), which bounds overloads and keeps assignments fair.

---

## Installation

Requires Python 3.10 or later.

```bash
git clone https://github.com/MendrikaRkt/university-lab-scheduler.git
cd university-lab-scheduler

# (recommended) create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate

# install runtime dependencies
pip install -r requirements.txt

# for development and tests
pip install -r requirements-dev.txt
```

You can also install the package itself in editable mode:

```bash
pip install -e .
```

---

## Usage

### Run the web interface

```bash
streamlit run presentation/app.py
```

The interface guides you through configuration, scheduling and result
inspection. It also includes a monitoring dashboard and a dry-run preview
sandbox to test configurations without writing any Excel file.

> Note: when run on a remote machine, the Streamlit server runs on that
> machine, not on your local computer. To use it locally, download the files
> and run the command on your own machine.

### Programmatic usage

```python
from application.use_cases.run_scheduling import RunSchedulingUseCase

uc = RunSchedulingUseCase()                 # loads config.yaml automatically
result = uc.execute(groups, professors)     # solve + allocate + validate
uc.export_excel("schedule.xlsx", result, groups, professors)

print(result.status)            # OPTIMAL / FEASIBLE
print(result.conflicts)         # residual conflicts
print(result.discrepancies)     # credit-vs-session gaps
```

---

## Deployment

The application is production-ready and ships with logging, a health check,
input validation, rate limiting and ready-to-use deployment configuration. See
[DEPLOYMENT.md](DEPLOYMENT.md) for the full step-by-step guide (Streamlit
Community Cloud, Docker, and systemd) and [SECURITY.md](SECURITY.md) for the
security model.

### Quick start with Docker

```bash
cp .env.example .env            # adjust LOG_LEVEL, APP_PORT if needed
docker compose up -d            # build and start on http://localhost:8501
docker compose logs -f          # follow logs
```

### Quick start with the helper script

```bash
./scripts/deploy.sh docker      # build image and run the container
./scripts/deploy.sh local       # run directly with a local virtual environment
./scripts/deploy.sh logs        # tail container logs
./scripts/deploy.sh stop        # stop and remove the container
```

### Streamlit Community Cloud

Point a new Streamlit Cloud app at this repository with
`presentation/app.py` as the entry point, set any secrets in the app's
"Secrets" panel, and deploy. Details are in [DEPLOYMENT.md](DEPLOYMENT.md).

### Production features

- **Health check**: a "Health & status" page in the UI plus the native
  `/_stcore/health` endpoint used by the Docker `HEALTHCHECK`.
- **Logging**: leveled logging (INFO/WARNING/ERROR) to console and rotating
  files under `logs/`, configured by `config/logging.yaml` and overridable with
  `LOG_LEVEL`.
- **Error handling**: domain errors are mapped to user-friendly messages.
- **Security**: upload validation, filename sanitization, solver rate limiting,
  XSRF/CORS protection and a non-root container.
- **Performance**: caching utilities and progress indicators for long solves.

---

## Tests

```bash
pytest -q
```

Coverage of the critical components:

- `test_credit_system.py` - credit rule, overload/underload detection
- `test_excel_reader.py` - subject matching and P/TP credit parsing (theory ignored)
- `test_conflict_detector.py` - C1/C4/C5 conflicts and student double-booking
- `test_config_loader.py` - faithful externalization of the configuration (22 subjects)
- `test_solver_engine.py` - week assignment, room constraints, teacher allocation, end-to-end
- `test_assignment_report.py` - validation report and Excel generator output
- `test_integration_real_file.py` - optional, runs only if the real dataset is present

---

## Continuous integration

Two GitHub Actions workflows run automatically on every push and pull request:

- `.github/workflows/tests.yml` - runs the pytest suite on multiple Python versions.
- `.github/workflows/lint.yml` - runs `ruff` for static analysis and style checks.

---

## Extensibility

- **New subject**: add an entry in `config.yaml` (no code).
- **New optimization engine**: implement the `SchedulingSolver` port.
- **New export format**: add a class in `infrastructure/excel`.
- **New constraint**: add a method to `ConstraintManager` plus a `Constraint`
  entry for the audit trail.

---

## Contributing

Contributions are welcome. The project uses a pull-request workflow:

1. Fork the repository and create a feature branch from `main`:
   `git checkout -b feature/my-change`.
2. Make your changes and keep the codebase in English with no emojis.
3. Run the test suite and the linter locally:
   `pytest -q && ruff check .`.
4. Commit with a clear message and push your branch.
5. Open a pull request describing the change and the motivation.

Please do not merge your own pull requests without review.

---

## License

This project is licensed under the terms of the MIT License. See the
[LICENSE](LICENSE) file for details.
