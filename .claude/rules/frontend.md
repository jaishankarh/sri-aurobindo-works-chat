---
globs: "frontend/**/*"
---
# Frontend Architecture Rules

- **Stack**: React 18 + Vite (not Next.js — no App Router, no Server Components). Plain SPA.
- **Component Creation**: Functional components using arrow functions. Write styles exclusively
  with Tailwind utility classes.
- **State Isolation**: Keep the three Zustand stores separate and never merge them:
  - `useChatStore` — updated on every LLM token (~50/s during streaming)
  - `usePDFStore` — only updated when citations are clicked or pages change
  - `useSettingsStore` — persisted to localStorage, updated only on user interaction
  This isolation exists so token streaming never triggers PDF canvas re-renders.
- **File Structure**: Components live under `frontend/src/components/<Feature>/`; hooks under
  `frontend/src/hooks/`; stores under `frontend/src/stores/`; shared types under `frontend/src/types/`.
- **PDF Coordinates**: Bounding-box transforms in `frontend/src/utils/coordinates.ts` must stay in
  sync with the backend's `spatial_parser.py` (bottom-left → top-left origin conversion).
