# Getting Started - Complete Action Plan

## 📋 Complete Checklist

### Phase 1: Local Setup (15 minutes)
- [ ] Clone repository to your local PC
- [ ] Set up Python virtual environment
- [ ] Install all dependencies
- [ ] Verify installation with tests
- [ ] Run the application locally

### Phase 2: GitHub CI/CD Activation (10 minutes)
- [ ] Manually add GitHub Actions workflows
- [ ] Enable GitHub Actions in repository settings
- [ ] Verify automated tests run successfully

### Phase 3: Data Preparation (20 minutes)
- [ ] Prepare your Excel data files
- [ ] Update configuration if needed
- [ ] Test with real data
- [ ] Verify results

### Phase 4: Deployment (Optional, 30 minutes)
- [ ] Choose deployment method
- [ ] Deploy to production
- [ ] Test deployed application

---

## 🚀 Phase 1: Local Setup

### Step 1: Clone the Repository

Open your terminal/command prompt and run:

```bash
# Navigate to your preferred directory
cd ~/Documents  # Or C:\Users\YourName\Documents on Windows

# Clone the repository
git clone https://github.com/MendrikaRkt/university-lab-scheduler.git

# Navigate into the project
cd university-lab-scheduler
```

### Step 2: Set Up Python Virtual Environment

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` at the beginning of your command prompt.

### Step 3: Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (for testing)
pip install -r requirements-dev.txt
```

### Step 4: Verify Installation

Run the test suite to ensure everything is working:

```bash
pytest
```

**Expected output:** All 46 tests should pass with green checkmarks.

If you see any errors, check:
- Python version (should be 3.9+): `python --version`
- All dependencies installed: `pip list`

### Step 5: Run the Application Locally

```bash
streamlit run presentation/app.py
```

The application will open automatically in your browser at `http://localhost:8501`

**Test the following:**
1. Navigate through the wizard (Configuration, Run, Results)
2. Try the "Health & Status" page from the sidebar
3. Check the "Configuration" page to see all loaded subjects

---

## 💧 Phase 2: GitHub CI/CD Activation

Since GitHub App restrictions prevented automatic workflow push, you need to add them manually:

### Step 1: Verify Workflows Exist Locally

Check if workflow files exist:

```bash
ls -la .github/workflows/
```

You should see:
- `tests.yml` - Automated testing
- `lint.yml` - Code quality checks

### Step 2: Push Workflows to GitHub

**Option A: Via Git Command Line (Recommended)**

```bash
# Make sure you're on the main branch
git checkout main

# Add workflow files
git add .github/workflows/

# Commit
git commit -m "ci: Add GitHub Actions workflows for automated testing and linting"

# Push to GitHub
git push origin main
```

**Option B: Via GitHub Web Interface**

If the above doesn't work due to permissions:

1. Go to: https://github.com/MendrikaRkt/university-lab-scheduler
2. Click "Add file" → "Create new file"
3. Name it: `.github/workflows/tests.yml`
4. Copy content from your local `.github/workflows/tests.yml`
5. Commit directly to main
6. Repeat for `lint.yml`

### Step 3: Enable GitHub Actions

1. Go to: https://github.com/MendrikaRkt/university-lab-scheduler/settings/actions
2. Under "Actions permissions", select "Allow all actions and reusable workflows"
3. Click "Save"

### Step 4: Verify CI/CD Works

1. Make a small change (e.g., edit README.md)
2. Commit and push:
   ```bash
   git add README.md
   git commit -m "test: Verify CI/CD pipeline"
   git push origin main
   ```
3. Go to: https://github.com/MendrikaRkt/university-lab-scheduler/actions
4. You should see the workflow running
5. Wait for green checkmarks ✓

---

## 📊 Phase 3: Data Preparation

### Step 1: Prepare Your Excel Files

You need these files in a `data/` folder:

```bash
# Create data directory
mkdir -p data

# Copy your files (adjust paths as needed)
cp ~/Downloads/Asignacion_2025-2026_v5.xlsx data/
cp ~/Downloads/informeDetalleGruposPorCurso.xls data/
```

### Step 2: Update Configuration (if needed)

Edit `config/config.yaml` to match your specific needs:

```bash
# Use your preferred editor
nano config/config.yaml
# or
code config/config.yaml  # VS Code
```

**Key sections to review:**
- `paths:: - Update file paths to point to your data files
- `subjects:` - Verify all 22 subjects are correctly configured
- `solver:` - Adjust time_limit if needed (default: 30s)

### Step 3: Test with Real Data

```bash
# Run the application
streamlit run presentation/app.py
```

**Testing workflow:**
1. Go to "Configuration" page - verify subjects are loaded
2. Click "Run Scheduler" (wizard step 2)
3. Check "Results" page - verify:
   - No conflicts detected
   - Credit discrepancies are within tolerance
   - Professor assignments are correct
4. Download the generated Excel file
5. Open Excel file and verify:
   - "Subject View" sheet has correct sessions
   - "Teacher View" sheet shows detailed schedule per professor
   - "Validation" sheet shows credit audit

### Step 4: Verify Professor Credit System

**Critical verification:**
- Open the generated Excel "Validation" sheet
- Check that each professor's assigned sessions match their practice credits
- Formula: **Expected Sessions = Practice Credits × 5**
- Look for status indicators:
  - ✓ OK (green) - Balanced
  - ⚠ SUR (orange) - Overload
  - ⚠ SOUS (yellow) - Underload

---

## 🌐 Phase 4: Deployment (Optional)

### Option A: Streamlit Cloud (Easiest - Recommended for Demo)

**Advantages:** Free, fast, no server management

1. Go to: https://streamlit.io/cloud
2. Sign in with GitHub
3. Click "New app"
4. Select repository: `MendrikaRkt/university-lab-scheduler`
5. Branch: `main`
6. Main file path: `presentation/app.py`
7. Click "Deploy"
8. Wait 2-3 minutes
9. Your app will be live at: `https://your-app-name.streamlit.app`

**Note:** Streamlit Cloud apps sleep after inactivity but wake up when accessed.

### Option B: Docker Deployment (Production-Ready)

**Advantages:** Isolated, reproducible, can run on any server

```bash
# Build the Docker image
docker build -t lab-scheduler:latest .

# Run the container
docker run -d \
  --name lab-scheduler \
  -p 8501:8501 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/outputs:/app/outputs \
  lab-scheduler:latest

# Check if running
docker ps

# View logs
docker logs lab-scheduler

# Access the app
# Open browser: http://localhost:8501
```

**For production server:**
```bash
# Using docker-compose (recommended)
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### Option C: Traditional Server (systemd)

**For Linux servers:**

```bash
# Copy deployment script
sudo cp scripts/deploy.sh /usr/local/bin/lab-scheduler-deploy
sudo chmod +x /usr/local/bin/lab-scheduler-deploy

# Copy systemd service
sudo cp deploy/lab-scheduler.service /etc/systemd/system/

# Edit service file to match your paths
sudo nano /etc/systemd/system/lab-scheduler.service

# Enable and start service
sudo systemctl enable lab-scheduler
sudo systemctl start lab-scheduler

# Check status
sudo systemctl status lab-scheduler

# View logs
sudo journalctl -u lab-scheduler -f
```

---

## 💀 Daily Workflow: Making Changes

### Create a Feature Branch

```bash
# Update main branch
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/improve-credit-allocation

# Make your changes...
# Edit files as needed

# Check what changed
git status
git diff

# Stage changes
git add .

# Commit with descriptive message
git commit -m "feat: Improve professor credit allocation algorithm"

# Push to GitHub
git push origin feature/improve-credit-allocation
```

### Create Pull Request

1. Go to: https://github.com/MendrikaRkt/university-lab-scheduler
2. Click "Compare & pull request" button
3. Fill in PR template:
   - Title: Brief description
   - Description: What changed and why
4. Click "Create pull request"
5. Wait for CI/CD checks to pass
6. Review the changes
7. Click "Merge pull request" when ready

---

## 🐛 Troubleshooting

### Issue: Tests Fail Locally

**Solution:**
```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt -r requirements-dev.txt

# Clear pytest cache
rm -rf .pytest_cache

# Run tests with verbose output
pytest -v
```

### Issue: Streamlit Won't Start

**Solution:**
```bash
# Check if port 8501 is in use
# Windows:
netstat -ano | findstr :8501
# macOS/Linux:
lof -i :8501

# Kill the process or use different port
streamlit run presentation/app.py --server.port 8502
```

### Issue: Excel Files Not Found

**Solution:**
```bash
# Check config paths
cat config/config.yaml | grep paths

# Verify files exist
ls -la data/

# Update paths in config.yaml to match your file locations
```

### Issue: Permission Denied on Linux/macOS

**Solution:**
```bash
# Make scripts executable
chmod +x scripts/*.sh

# Or run with explicit interpreter
bash scripts/deploy.sh
```

---

## 📞 Next Steps for Your Presentation

### 1. Practice the Demo (2-3 times)

**Demo Script:**
1. **Introduction** (1 min)
   - "This is an AI-powered lab scheduler using CP-SAT optimization"
   
2. **Show Configuration** (1 min)
   - Open app → Configuration page
   - "22 subjects configured, each with specific constraints"
   
3. **Run Scheduler** (2 min)
   - Click "Run Scheduler"
   - Show progress bar
   - Explain what's happening: "Solver is optimizing 357 constraints..."
   
4. **Show Results** (3 min)
   - Results page: "All sessions scheduled, zero conflicts"
   - "Professor assignments respect their credit allocations"
   
5. **Show Monitoring** (2 min)
   - Monitoring Dashboard: Metrics, stats
   - Preview Sandbox: "Can test scenarios without generating files"
   
6. **Show Output** (1 min)
   - Download and open Excel file
   - Show "Teacher View" with detailed schedules
   - Show "Validation" sheet with credit audit

**Total: 10 minutes + 5 min Q&A**

### 2. Prepare Backup Materials

- Print PDF documentation in case of technical issues
- Have PowerPoint ready on USB stick
- Take screenshots of key screens
- Prepare sample Excel output to show

### 3. Anticipate Questions

**Expected questions:**
1. "How does the solver handle conflicts?"
    → "Uses CP-SAT constraint satisfaction, guaranteed zero conflicts"

2. "Can it scale to other universities?"
    → "Yes, just update config.yaml - no code changes needed"

3. "How long does optimization take?"
    → "Less than 10 seconds for 22 subjects, 100+ sessions"

4. "What if professor assignments change?"
    → "Update Excel file, re-run solver - takes seconds"

---

## ✅ Final Pre-Presentation Checklist

**3 Days Before:**
- [ ] Clone repo on your local PC
- [ ] Run all tests successfully
- [ ] Generate sample output with real data
- [ ] Practice demo 2-3 times

**1 Day Before:**
- [ ] Verify app runs smoothly
- [ ] Check all documentation is accessible
- [ ] Prepare backup materials
- [ ] Rehearse Q&A answers

**Day Of:**
- [ ] Arrive 15 minutes early
- [ ] Test projector connection
- [ ] Open app and have it ready
- [ ] Have backup materials accessible
- [ ] Deep breath, you got this! 🎆

---

## 📚 Documentation Reference

All documentation is in English, as requested:

- **README.md** - Project overview and quick start
- **DEPLOYMENT.md** - Detailed deployment guide
- **SECURITY.md** - Security best practices
- **Lab_Scheduler_Technical_Documentation.pdf** - 26-page technical report
- **University_Lab_Scheduler.pptx** - 18-slide presentation

Good luck with your presentation! 🚀
