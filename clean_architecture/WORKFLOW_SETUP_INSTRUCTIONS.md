# GitHub Actions Workflow Setup Instructions

## 🚨 Important: Manual Setup Required

Due to GitHub security restrictions, workflow files (`.github/workflows/*.yml`) cannot be automatically pushed by third-party applications. You must add them manually.

## 📋 Quick Setup (5 minutes)

### Option 1: Via Web Interface (Easiest)

**Step 1: Enable GitHub Actions**
1. Go to: https://github.com/MendrikaRkt/university-lab-scheduler/settings/actions
2. Under "Actions permissions", select: **"Allow all actions and reusable workflows"**
3. Click **"Save"**

**Step 2: Add tests.yml workflow**
1. Go to: https://github.com/MendrikaRkt/university-lab-scheduler
2. Click **"Add file"** → **"Create new file"**
3. Type filename: `.github/workflows/tests.yml`
4. Copy and paste this content:

```yaml
name: Tests

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Run tests
      run: pytest -v
    
    - name: Test coverage
      run: pytest --cov=. --cov-report=term-missing
```

5. Commit directly to `main` branch

**Step 3: Add lint.yml workflow**
1. Click **"Add file"** → **"Create new file"**
2. Type filename: `.github/workflows/lint.yml`
3. Copy and paste this content:

```yaml
name: Lint

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  lint:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install ruff
      run: pip install ruff
    
    - name: Run ruff
      run: ruff check .
```

4. Commit directly to `main` branch

**Step 4: Verify**
1. Go to: https://github.com/MendrikaRkt/university-lab-scheduler/actions
2. You should see workflows running
3. Wait for green checkmarks ✓

---

### Option 2: Via Git from Your Local Machine

**Prerequisites:** You must have cloned the repo on your PC and be in the project directory.

```bash
# Navigate to your local clone
cd ~/Documents/university-lab-scheduler  # Adjust path as needed

# Copy workflow files from the template (they already exist locally)
git pull origin main

# The .github/workflows/ directory should already exist locally
# with tests.yml and lint.yml files

# Add them to git
git add .github/workflows/

# Commit
git commit -m "ci: Add GitHub Actions workflows"

# Push using YOUR GitHub credentials (not Abacus app)
git push origin main
```

**Note:** You'll need to authenticate with your own GitHub account (not the Abacus app token).

---

## ✅ Verification Checklist

After setup, verify everything works:

- [ ] Go to: https://github.com/MendrikaRkt/university-lab-scheduler/actions
- [ ] You see both "Tests" and "Lint" workflows
- [ ] Latest workflow runs show green checkmarks
- [ ] Badge shows passing status

---

## 🔍 Troubleshooting

### "Actions not appearing"
- Check that you enabled Actions in Settings → Actions
- Refresh the page after adding workflows

### "Workflow failed"
- Click on the failed workflow to see error details
- Most common issues:
  - Missing dependencies in requirements.txt
  - Python version mismatch
  - Test failures (fix tests first)

### "Permission denied"
- Make sure you're logged in with your GitHub account
- Check that you have write access to the repository

---

## 🎯 What Happens After Setup

Once workflows are active:

1. **Every push to `main`**: Tests and lint checks run automatically
2. **Every pull request**: CI/CD validates changes before merge
3. **Status badges**: Show build status on README
4. **Quality gates**: Prevent broken code from being merged

---

## 📞 Need Help?

- GitHub Actions Documentation: https://docs.github.com/en/actions
- Repository Actions: https://github.com/MendrikaRkt/university-lab-scheduler/actions
- Check workflow logs for detailed error messages
