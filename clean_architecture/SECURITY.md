# Security

This document describes the security model of the University Lab Scheduler and
the best practices to follow when deploying it. The application is a single
internal tool (no user accounts, no public write API), so the threat model is
focused on safe handling of uploaded spreadsheets, secrets, and the web server
surface exposed by Streamlit.

## Reporting a vulnerability

If you discover a security issue, please do not open a public issue. Contact the
maintainer privately (for example through a direct message on the repository
host) with a description, reproduction steps and the affected version. You will
receive an acknowledgement, and a fix will be prioritized.

## Secrets management

- Never commit secrets. `.env`, `.env.*` (except `.env.example`) and
  `.streamlit/secrets.toml` are ignored by `.gitignore`.
- Use `.env.example` and `.streamlit/secrets.toml.example` as templates and copy
  them to the real, untracked files on each environment.
- In Docker, inject secrets with `env_file` or `--env-file`, never bake them
  into the image.
- On Streamlit Community Cloud, store secrets in the app's "Secrets" panel; they
  are exposed at runtime through `st.secrets`.
- Rotate any secret that is accidentally committed and purge it from history.

## Input validation and sanitization

All user-provided input is validated in `infrastructure/security.py`:

- `validate_upload` rejects files whose extension is not in
  `ALLOWED_UPLOAD_EXTENSIONS` (`.xlsx`, `.xls`, `.csv`) and whose size exceeds
  `MAX_UPLOAD_BYTES` (25 MB). The same 25 MB cap is enforced by Streamlit via
  `maxUploadSize` in `.streamlit/config.toml`.
- `sanitize_filename` strips directory components and unsafe characters to
  prevent path-traversal when a name is reused for an output file.
- `sanitize_text` removes control characters and bounds the length of free-text
  fields.
- `validate_int` enforces numeric ranges for parameters that reach the solver,
  preventing pathological values.

Spreadsheets are parsed with `openpyxl` / `pandas` in read-only mode. The
application never evaluates spreadsheet formulas or macros.

## Rate limiting

A thread-safe sliding-window `RateLimiter` (`infrastructure/security.py`) guards
the most expensive operation, the CP-SAT solve. The UI limits solver runs to a
fixed number per rolling window and shows a friendly "try again later" message
when the limit is hit, which protects the host from accidental or abusive
repeated submissions.

## Web server hardening

- `.streamlit/config.toml` enables XSRF protection (`enableXsrfProtection`) and
  CORS protection (`enableCORS`), disables usage statistics
  (`gatherUsageStats = false`), and hides internal error details from end users
  (`showErrorDetails = false`).
- Run the app behind a reverse proxy (nginx, Caddy, Traefik) that terminates
  TLS, sets security headers and forwards only the Streamlit port. Do not expose
  the raw Streamlit port to the public internet.
- The container runs as a non-root user (`appuser`) and ships a `HEALTHCHECK`
  so orchestrators can restart unhealthy instances.

## Dependency and supply-chain hygiene

- Runtime dependencies are pinned with lower bounds in `requirements.txt`; the
  Docker build installs them in an isolated virtual environment in a builder
  stage and copies only the result into the runtime image.
- Keep dependencies current and review advisories (for example with
  `pip list --outdated` or `pip-audit`) before each release.
- The CI pipeline runs `ruff` and the test suite on every push and pull request.

## Logging and data exposure

- Logs are written to `logs/app.log` and `logs/error.log` with rotation
  (`config/logging.yaml`). They record operational events, not spreadsheet
  contents.
- `logs/` is git-ignored so log data never lands in version control.
- The health page and `/_stcore/health` endpoint expose only component status,
  never configuration values or secrets.

## Deployment checklist

- [ ] Real secrets live only in untracked `.env` / `secrets.toml` or the host's
      secret store.
- [ ] TLS terminated by a reverse proxy; Streamlit port not publicly exposed.
- [ ] Container or service runs as a non-root user.
- [ ] Upload size and extension limits are in force.
- [ ] Health check is wired into the orchestrator.
- [ ] Dependencies reviewed for known advisories.
