# Agent Instructions

StabilityNet is built incrementally. Keep the repository runnable after every
phase and prefer clear, testable modules over broad infrastructure.

## Working Rules

- Read `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, and
  `docs/AGENT_STATE.md` before changing code.
- Keep Phase 1 focused on an offline video pipeline.
- Do not add services, queues, databases, or frontend code until the pipeline
  produces useful structured output.
- Treat mobility events as indicators, not diagnoses.
- Record meaningful architecture decisions in `docs/DECISIONS.md`.
- Record implementation lessons in `docs/LESSONS.md`.

## Current Stack

- Python
- PyTorch through Ultralytics YOLOv8n
- OpenCV
- NumPy
- SORT-style tracking
- FastAPI
- Redis
- PostgreSQL
- React
- TypeScript

