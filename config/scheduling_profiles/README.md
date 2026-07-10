# Scheduling Profiles

This directory contains **scheduling profile definitions** that configure the generic scheduling engine for different university planning domains.

## What is a Scheduling Profile?

A profile is a YAML configuration file that defines:
- **Domain-specific rules** (e.g., "1 P credit = 5 lab sessions" vs. "1 exam per subject")
- **Constraints** (hard requirements and soft preferences)
- **Room/instructor assignment logic**
- **Output format** (which Excel sheets to generate)

The same underlying CP-SAT solver can then handle **multiple scheduling problems** (lab practices, final exams, lecture hall assignment, etc.) by simply loading different profiles.

## Available Profiles

| Profile | Domain | Use Case | Status |
|---------|--------|----------|--------|
| [`lab_practice.yaml`](lab_practice.yaml) | Lab session planning | Current production use case | ✅ Active |
| [`final_exam.yaml`](final_exam.yaml) | Final exam scheduling | Hypothetical demo scenario | 📋 Proposal |

## Profile Structure

```yaml
# Meta
domain: lab_practice | final_exam | lecture_hall | ...
entity_label: Group | Exam | Course | ...
sessions_per_entity: 5  # How many times the entity is scheduled

# Time window
scheduling_weeks:
  min: 1
  max: 15
allow_repetitions: true | false

# Constraints
hard_constraints:
  - student_conflict
  - room_capacity
  - instructor_conflict
  - ...

soft_constraints:
  spacing: 200
  parity: 50
  ...

# Room rules
room_filter:
  type: lab_rooms | exam_rooms | lecture_halls
  min_capacity: 40
  
capacity_mode: per_group | aggregate

# Instructor rules
instructor_fixed: true | false
instructor_required: true | false

# Output
output_sheets:
  - name: "Sheet Name"
    description: "What this sheet contains"
```

## How to Use a Profile

### Option 1: CLI (future)
```bash
python pipeline.py --profile config/scheduling_profiles/final_exam.yaml
```

### Option 2: Streamlit UI (future)
- Navigate to **Multi-Profile** page
- Select profile from dropdown
- Configure data sources
- Run solver

### Option 3: Python API (current stub)
```python
from scheduling_core import SchedulingProfile, solve_generic

# Load profile
profile = SchedulingProfile.from_yaml("config/scheduling_profiles/lab_practice.yaml")

# Prepare data
entities = ...  # pd.DataFrame of groups/exams
time_slots = ...  # pd.DataFrame of available slots
busy_slots = ...  # Dict of conflicts

# Solve
schedule = solve_generic(entities, time_slots, busy_slots, profile, solver_config)
```

## Creating a Custom Profile

1. **Copy an existing profile** as a template
2. **Modify constraints** to match your domain:
   - Change `sessions_per_entity` (e.g., 3 instead of 5)
   - Add/remove hard constraints
   - Adjust soft constraint weights
3. **Update room/instructor rules** for your institution
4. **Define output sheets** you need
5. **Save as** `config/scheduling_profiles/my_custom.yaml`
6. **Test** with your data

## Strategic Vision

This profile system enables:
- ✅ **Multi-department usage** (Engineering labs, Business exams, etc.)
- ✅ **Multi-institution** (any university can adapt by creating their profile)
- ✅ **Rapid prototyping** (test "what if" scenarios by tweaking a YAML file)
- ✅ **No code changes** required for new scheduling domains

See [`docs/MULTI_DEPARTMENT_ABSTRACTION.md`](../../docs/MULTI_DEPARTMENT_ABSTRACTION.md) for the full architectural vision.
