# CI/CD Setup for the Clean Architecture Module

The Clean Architecture module ships two ready-to-use GitHub Actions workflows:

| Reference file        | Purpose                                  |
|-----------------------|------------------------------------------|
| `ci/tests.yml`        | Runs the pytest suite on Python 3.11/3.12|
| `ci/lint.yml`         | Runs `ruff` static analysis              |

Both are scoped with `paths: clean_architecture/**`, so they only run when this
module changes and never interfere with the legacy pipeline at the repository
root.

## Why are they under `ci/` and not `.github/workflows/`?

GitHub Apps (including the one used to open the integration Pull Request) are
**not allowed to create or update files under `.github/workflows/`** without the
dedicated `workflows` permission. To keep the PR clean and avoid a push
rejection, the workflows are provided here as reference files that you activate
manually in a few seconds.

This mirrors the convention already used by the legacy project
(`docs/ci.yml.reference`).

## How to activate (2 minutes)

### Option A - GitHub web interface (easiest)

1. Open the repository on GitHub.
2. Click **Add file -> Create new file**.
3. Name it `.github/workflows/clean-architecture-tests.yml`.
4. Paste the contents of `clean_architecture/ci/tests.yml`.
5. Commit to a branch and open a PR (or commit to `main` if you have rights).
6. Repeat for `.github/workflows/clean-architecture-lint.yml` using
   `clean_architecture/ci/lint.yml`.

### Option B - From your local clone

```bash
cd LabScheduling
mkdir -p .github/workflows
cp clean_architecture/ci/tests.yml .github/workflows/clean-architecture-tests.yml
cp clean_architecture/ci/lint.yml  .github/workflows/clean-architecture-lint.yml

git add .github/workflows/
git commit -m "ci: activate Clean Architecture workflows"
git push origin <your-branch>     # push with your own GitHub account
```

> Pushing workflow files requires your personal GitHub credentials (not the
> integration app token).

## Verify

After activation, open the **Actions** tab on GitHub. On the next push or PR
touching `clean_architecture/`, you should see:

- **Clean Architecture - Tests** -> green (46 tests pass)
- **Clean Architecture - Lint** -> green (ruff clean)

## Notes on action versions

The workflows pin `actions/checkout@v6` and `actions/setup-python@v6`. These
versions run on **Node.js 24**. Older `@v4`/`@v5` target the now-deprecated
Node.js 20 runtime and will emit failures/warnings on current GitHub runners.
