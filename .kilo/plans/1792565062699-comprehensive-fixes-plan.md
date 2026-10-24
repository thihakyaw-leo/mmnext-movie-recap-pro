# Comprehensive Fix Plan: Code Review Findings

## Overview
Address all items from the code review in 5 phases, maintaining existing architecture (ui -> application -> services -> domain), no GUI thread blocking, REAL/DEMO separation, Exact Dubbing immutability, and all existing contracts.

## Phase 1: Critical Safety Fixes

### 1.1 Correct Exact Dubbing translation use
- **Issue**: Ensure exact dubbing doesn't use narrator translation path incorrectly
- **Files**: `mmnext/application/exact_dubbing_service.py`, `mmnext/ui/app_context.py`
- **Action**: Verify exact dubbing uses its own translation/export flow; ensure no cross-contamination between narrator and exact-dubbing
- **Test**: `tests/test_exact_dubbing_render.py` already exists - ensure separation

### 1.2 Make REAL Narrator failures fail visibly
- **Issue**: REAL narrator failures should not be hidden/silenced
- **Files**: `mmnext/application/narrator_pipeline_coordinator.py`, `mmnext/ui/app_context.py`, `mmnext/ui/narrator_pipeline_worker.py`
- **Action**: Ensure all failures in REAL mode surface with clear messages; no silent fallbacks
- **Test**: Add/verify tests for failure visibility

### 1.3 Remove silent Common Editing DEMO fallback
- **Issue**: In REAL mode without FFmpeg, must fail explicitly not fall back to DEMO
- **Files**: `mmnext/ui/app_context.py` (start_common_editing_export)
- **Action**: Already partially addressed - ensure complete fix
- **Test**: Add test for REAL mode failure when tools missing

## Phase 2: Thread Management & Dirty State Protection

### 2.1 Protect dirty work on source change
- **Issue**: Changing source must check for unsaved edits
- **Files**: `mmnext/application/project_controller.py`, `mmnext/ui/app_context.py`
- **Action**: In `set_source()`, if non-demo session has dirty edits and source changes, require explicit discard or raise error
- **Test**: Add test for dirty protection

### 2.2 Manage reopen/Common Editing threads on Stop and close
- **Issue**: Threads must be stopped cleanly on app close/stop
- **Files**: `mmnext/ui/app_context.py`, `mmnext/ui/main_window.py`
- **Action**: Add `stop_all_threads()`, call on closeEvent; ensure threads are stopped/joined properly
- **Test**: Verify no thread leaks

### 2.3 Reject stale reopen results
- **Issue**: Stale results must be discarded
- **Files**: `mmnext/ui/app_context.py` (already has _reopen_token/_reopen_request_id)
- **Action**: Verify and harden existing logic
- **Test**: Already covered in `tests/test_transcript_reopen_thread.py`

## Phase 3: Security & Validation Hardening

### 3.1 Harden checkpoint validation
- **Files**: `mmnext/infrastructure/repository/job_repository.py`
- **Action**: Stricter schema validation, type checking, bounds checking

### 3.2 job_id containment
- **Files**: `mmnext/infrastructure/repository/job_repository.py`
- **Action**: Sanitize job_id to prevent path traversal (allow only safe chars)

### 3.3 job-scoped checkpoints
- **Files**: Already implemented, verify paths are properly scoped

### 3.4 artifact duration validation
- **Files**: `mmnext/infrastructure/transcript_adapter.py`
- **Action**: Already has validation, strengthen checks

### 3.5 per-render work directories
- **Files**: `mmnext/application/splitter_render_coordinator.py`, `mmnext/infrastructure/splitter_render.py`
- **Action**: Ensure each render uses isolated work dirs

## Phase 4: Specific Component Fixes

### 4.1 Splitter failure propagation/cache identity
- **Files**: `mmnext/application/splitter_render_coordinator.py` (already fixed fingerprint)
- **Action**: Ensure failures propagate correctly

### 4.2 Common Editing atomic output
- **Files**: `mmnext/services/adapters/common_editing.py`, `mmnext/infrastructure/ffmpeg_tools.py`
- **Action**: Use atomic write/rename pattern

### 4.3 Exact Dubbing duration validation
- **Files**: `mmnext/infrastructure/exact_dubbing_render.py`
- **Action**: Strengthen validation

## Phase 5: UI, Gates & Tests

### 5.1 Connect Settings/Resume UI
- **Files**: `mmnext/ui/screens/settings_screen.py`, `mmnext/ui/screens/jobs_screen.py`
- **Action**: Wire resume functionality

### 5.2 Repair optional smoke tests
- **Files**: Tests that may be broken
- **Action**: Fix any broken optional tests

### 5.3 Expand architecture gates
- **Files**: `tests/test_architecture_gates.py`
- **Action**: Add gates for new rules

### 5.4 Regression coverage
- **Files**: Add tests for each fix

## Validation
- Run focused tests for each area
- Run full suite: `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider`
- Run offscreen smoke: `$env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe scripts\check_shell.py`
- Update todo plan.md and checklist.md

## Constraints
- No GUI thread blocking
- REAL/DEMO separation strict
- Exact Dubbing immutability preserved
- No narrator/exact dubbing cross-contamination
- Use existing patterns and contracts
- No external network required for tests
