# 👨‍🏫 Teacher Availability Configuration Guide

## Overview

The **Teacher Availability** configuration page has been enhanced with **3 distinct options** to manage teacher constraints and preferences during lab scheduling optimization.

---

## 📋 Table of Contents

1. [Option 1: Days per week unavailable](#option-1-days-per-week-unavailable)
2. [Option 2: Specific day/time slots unavailable](#option-2-specific-datetime-slots-unavailable)
3. [Option 3: Preferred time range](#option-3-preferred-time-range)
4. [Comparison: Hard vs Soft Constraints](#comparison-hard-vs-soft-constraints)
5. [Usage Examples](#usage-examples)
6. [Technical Implementation](#technical-implementation)

---

## Option 1: Days per week unavailable

### 📅 Description
Block **entire weekdays** when a teacher is never available.

### 🚫 Type
**Hard constraint** - The teacher will NEVER be assigned on these days.

### Use cases
- Teacher doesn't work on specific weekdays (e.g., "Never works on Mondays")
- Part-time teachers with fixed unavailable days
- Teachers with recurring commitments on specific weekdays

### How to configure
1. Select the teacher from the dropdown
2. Select one or more unavailable weekdays (Lunes, Martes, Miércoles, Jueves, Viernes)
3. Click "Add"

### Example
```
Teacher: Roberto Fernández
Unavailable weekdays: Lunes, Viernes
→ Roberto will NEVER be scheduled on Mondays or Fridays
```

### Data structure
```python
st.session_state.advanced_config['teacher_unavailable_weekdays'] = {
    'Roberto Fernández': ['Lunes', 'Viernes'],
    'Beatriz Portillo': ['Miércoles']
}
```

---

## Option 2: Specific day/time slots unavailable

### 🕒 Description
Block **specific time slots** on specific days when a teacher cannot attend.

### 🚫 Type
**Hard constraint** - The teacher will NEVER be assigned to these exact slots.

### Use cases
- Teacher has a recurring meeting every Tuesday 10:30-12:30
- Teacher teaches another course at specific times
- Temporary unavailability on specific days

### How to configure
1. Select the teacher from the dropdown
2. Select the day (Lunes, Martes, Miércoles, Jueves, Viernes)
3. Select the time slot or "(All day)" to block the entire day
4. Click "Add"

### Available time slots
- 08:30-10:30
- 10:30-12:30
- 12:30-14:30
- 15:00-17:00
- 17:00-19:00
- 19:00-21:00
- **(All day)** - blocks all 6 time slots

### Example
```
Teacher: Daniel Álvarez
Unavailable: Martes 10:30-12:30, Jueves 15:00-17:00
→ Daniel will NEVER be scheduled on:
   - Tuesday 10:30-12:30
   - Thursday 15:00-17:00
```

### Data structure
```python
st.session_state.advanced_config['teacher_unavailability'] = {
    'Daniel Álvarez': [
        'Martes 10:30-12:30',
        'Jueves 15:00-17:00'
    ]
}
```

---

## Option 3: Preferred time range

### ⭐ Description
Define **soft preferences** for when a teacher prefers to work.

### ✅ Type
**Soft constraint** - The optimizer will TRY to respect these but won't block if impossible.

### Use cases
- Teacher prefers morning slots (08:30-12:30)
- Teacher prefers to work maximum 3 days per week
- Teacher prefers afternoon slots (15:00-19:00)

### How to configure
1. Select the teacher from the dropdown
2. Set "Max days/week" (0 = no limit, 1-5 = preferred maximum)
3. Select preferred time slots (multiple selection allowed)
4. Click "Set"

### Features
- **Max days/week**: Soft limit on the number of lab days per week
  - 0 = no limit
  - 1-5 = preferred maximum (warns if exceeded but doesn't block)
- **Preferred time slots**: Time slots the teacher prefers
  - Optimizer penalizes assignments outside this range
  - Never blocks if impossible to satisfy

### Example
```
Teacher: Alessio Zuliani
Max days/week: 3
Preferred time slots: 08:30-10:30, 10:30-12:30
→ Optimizer will:
   - Try to assign ≤3 days/week
   - Prefer morning slots (08:30-12:30)
   - Still assign if necessary even if it exceeds preferences
```

### Data structure
```python
st.session_state.advanced_config['teacher_preferences'] = {
    'Alessio Zuliani': {
        'max_days_per_week': 3,
        'preferred_blocks': [1, 2]  # Block indices (1-indexed)
    }
}
```

---

## Comparison: Hard vs Soft Constraints

| Feature | Hard Constraint 🚫 | Soft Constraint ✅ |
|---------|-------------------|-------------------|
| **Options** | Option 1, Option 2 | Option 3 |
| **Behavior** | NEVER violated | Optimizer tries to respect |
| **If impossible** | Schedule fails or finds alternative | Schedule continues with penalty |
| **Use case** | Absolute unavailability | Preferences |
| **Impact** | Blocks assignments | Penalizes but allows |

### Priority order
1. **Hard constraints** (Options 1 & 2) are checked first → Must be satisfied
2. **Soft constraints** (Option 3) are applied → Optimizer tries to minimize violations

---

## Usage Examples

### Example 1: Part-time teacher
```
Teacher: Maria García
Option 1: Unavailable weekdays = Lunes, Martes, Miércoles
Option 3: Max days/week = 2
→ Maria only works Thu/Fri, maximum 2 days per week
```

### Example 2: Teacher with recurring meeting
```
Teacher: Juan Pérez
Option 2: Martes 10:30-12:30 (hard block)
Option 3: Preferred slots = 08:30-10:30, 15:00-17:00
→ Juan is blocked on Tuesday 10:30-12:30, prefers early morning/afternoon
```

### Example 3: Morning-only teacher
```
Teacher: Ana López
Option 3: Preferred time slots = 08:30-10:30, 10:30-12:30, 12:30-14:30
Option 3: Max days/week = 4
→ Ana prefers mornings, maximum 4 days/week (soft)
```

### Example 4: Complex availability
```
Teacher: Carlos Ruiz
Option 1: Viernes (never available)
Option 2: Lunes 19:00-21:00, Miércoles 17:00-19:00 (hard blocks)
Option 3: Max days/week = 3, Preferred = 10:30-12:30, 12:30-14:30
→ Carlos:
   - Never on Friday
   - Blocked Monday evening, Wednesday afternoon
   - Prefers 3 days/week, midday slots
```

---

## Technical Implementation

### Session state structure
```python
st.session_state.advanced_config = {
    # Option 1: Days per week unavailable (hard)
    'teacher_unavailable_weekdays': {
        'Teacher Name': ['Lunes', 'Viernes', ...]
    },
    
    # Option 2: Specific day/time unavailable (hard)
    'teacher_unavailability': {
        'Teacher Name': [
            'Martes 10:30-12:30',
            'Jueves 15:00-17:00',
            ...
        ]
    },
    
    # Option 3: Preferences (soft)
    'teacher_preferences': {
        'Teacher Name': {
            'max_days_per_week': 3,           # int or None
            'preferred_blocks': [1, 2, 3]     # block indices (1-6)
        }
    }
}
```

### Block indices mapping
```python
Block index → Time slot
1 → 08:30-10:30
2 → 10:30-12:30
3 → 12:30-14:30
4 → 15:00-17:00
5 → 17:00-19:00
6 → 19:00-21:00
```

### Integration with optimizer
The configuration is saved in `advanced_config` and must be integrated with `pipeline.py` during optimization:

```python
def apply_teacher_constraints(model, ...):
    config = st.session_state.advanced_config
    
    # Apply hard constraints (Option 1)
    for teacher, unavailable_days in config.get('teacher_unavailable_weekdays', {}).items():
        # Block all slots on these days for this teacher
        pass
    
    # Apply hard constraints (Option 2)
    for teacher, unavailable_slots in config.get('teacher_unavailability', {}).items():
        # Block specific day/time slots for this teacher
        pass
    
    # Apply soft constraints (Option 3)
    for teacher, prefs in config.get('teacher_preferences', {}).items():
        if prefs.get('max_days_per_week'):
            # Add penalty if exceeds max days
            pass
        if prefs.get('preferred_blocks'):
            # Add penalty for assignments outside preferred blocks
            pass
```

---

## Benefits

### ✅ Clear separation
- **Option 1**: Weekday-level blocking
- **Option 2**: Slot-level blocking  
- **Option 3**: Preferences

### ✅ Flexibility
- Combine hard and soft constraints per teacher
- Multiple teachers can have different configurations

### ✅ User-friendly
- Visual icons and emojis for clarity
- Expandable sections to reduce clutter
- Clear descriptions of hard vs soft

### ✅ Robust
- Default values ensure no errors if config missing
- Validation before adding constraints
- Easy removal of configured constraints

---

## Backward Compatibility

### Old configuration (deprecated)
The old `teacher_rules` has been replaced by:
- `teacher_unavailable_weekdays` (new - Option 1)
- `teacher_unavailability` (existing - Option 2)
- `teacher_preferences` (replaces `teacher_rules` - Option 3)

### Migration
If you have old configurations, they should be migrated:

```python
# Old structure
st.session_state.advanced_config['teacher_rules'] = {
    'Teacher': {
        'max_days_per_week': 3,
        'preferred_blocks': [1, 2]
    }
}

# New structure (migrated to Option 3)
st.session_state.advanced_config['teacher_preferences'] = {
    'Teacher': {
        'max_days_per_week': 3,
        'preferred_blocks': [1, 2]
    }
}
```

---

## Future Enhancements

### Possible additions
1. **Import/Export** teacher configurations as CSV
2. **Bulk operations** for multiple teachers
3. **Templates** for common availability patterns
4. **Calendar view** to visualize teacher availability
5. **Conflict detection** before running optimization

---

## Support

For questions or issues:
1. Check the in-app tooltips (hover over ℹ️ icons)
2. Consult this guide
3. Contact the system administrator

---

**Version:** 2.0  
**Date:** June 18, 2026  
**Author:** Lab Scheduling Automation Team
