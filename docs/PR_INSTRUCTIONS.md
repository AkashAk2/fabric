# PR: Replace single-agent PPT generator with multi-agent Agno pipeline

Summary
- Replaced legacy single-agent flow with a deterministic, typed, multi-agent pipeline (Planner, Designer, ImageAgent, Critic, Fixer) using Agno (Gemini) with temperature=0.
- Enforced Infosys Consulting guidelines as a single source of truth and strict typed contracts (no regex JSON parsing).
- Rendered branded PPTX via template-aware executor, verified hard+soft checks, and iterated fixes until gates pass.

What changed
- New source of truth: services/guidelines.py (brand/content/visual rules, imagery policy, iteration settings).
- Typed contracts: models/contracts.py (Plan/Slide/Bullet/StyleHints/AssetManifest/QCItem/OrchestratorState) with length/count constraints.
- Agents (JSON-only outputs):
  - agents/planner.py: SCQA/Pyramid planning, slide purposes, assets.
  - agents/designer.py: style hints, fonts, palette, layouts mapping.
  - agents/image_agent.py: image prompts + alt text per slide.
  - agents/critic.py: soft QC against all guidelines.
  - agents/fixer.py: minimal plan fixes for BLOCKER/MAJOR.
- Executors:
  - executors/ppt_executor.py: template-aware renderer (.potx), 16:9, fonts, bullets, images with alt text.
  - executors/verifier.py: hard checks on PPTX (aspect, counts, fonts/sizes, bullets, required images, alt text).
- Orchestration: orchestrator.py runs the end-to-end loop with retries and deterministic settings.
- API: services/agno_service/app.py now exposes /generate and SSE (/generate-stream + /runs/{id}/stream), returns QC findings and ppt path.
- Theme placeholder: templates/master_theme.potx (to be replaced with the actual branded theme).
- Smoke test: services/agno_service/test_app.py (POST /generate on a retail cloud topic).
- Requirements: pinned to pydantic v2 and added google-genai; ensured temperature=0 in agents.

Removed/retired
- Legacy single-agent orchestration and regex JSON parsing removed from services/agno_service (main.py, ppt_orchestrator.py).

How to run (local)
- Ensure GOOGLE_GENAI_API_KEY is set if using non-Vertex mode, or configure VertexAI env vars. Start FastAPI app and call POST /generate with {"topic": "..."}.

Quality gates
- Unit tests: 1 smoke test passing. Hard verifier runs on actual PPTX; soft Critic checks guideline adherence.

Follow-ups (separate PRs)
- Replace templates/master_theme.potx with the official Infosys theme; update layout mappings accordingly.
- Expand verifier: palette enforcement, margins >=60px, WCAG contrast sampling, link checks, icon vector checks.
- Integrate a real image backend and auto alt-text improvements.
- Fabric UI: guideline selector, agent SSE lanes, PASS/FAIL chips, preview/download actions.

Suggested commit message
"feat(ppt): migrate to multi-agent Agno pipeline with typed contracts, branded rendering, and QC gates; add FastAPI endpoints and smoke test"
