# Contributing to LabMemory

Thank you for your interest in contributing to LabMemory! We welcome community contributions from bug fixes to architectural improvements.

---

## Code of Conduct

Please maintain professional, constructive, and respectful communication in all interactions across issues, pull requests, and discussions.

---

## Development Workflow

### 1. Prerequisites
- **Python**: >= 3.12 (recommend managing via `uv`)
- **Node.js**: >= 20 (recommend Node 22 LTS)
- **Database**: SQLite (built-in, with sqlite-vec extension support)

### 2. Fork and Clone
```bash
git clone https://github.com/<your-username>/LabMemory.git
cd LabMemory
```

### 3. Setup Platform
```bash
cd labmemory-platform
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Run tests to ensure everything is green:
```bash
pytest
```

### 4. Setup Frontend
```bash
cd labmemory-platform/frontend
npm install
npm run build
```

---

## OpenSpec Specification-First Principle

LabMemory follows **OpenSpec** methodology for system changes:
1. Core contracts and domain rules live in `openspec/specs/`.
2. Any breaking schema change, state machine transition alteration, or protocol modification must start with a proposal/delta under `openspec/changes/`.
3. Code implementation follows the approved spec delta.

---

## Commit Guidelines

We use conventional commit formatting:
- `feat:` New capability or endpoint
- `fix:` Bug fix or error handling
- `docs:` Documentation or guide updates
- `test:` Test coverage or test fixture update
- `chore:` Dependency update, tooling, or build configuration

Please avoid committing sensitive data (tokens, personal emails, server IPs, internal secrets). Ensure all pull requests pass existing test suites.
