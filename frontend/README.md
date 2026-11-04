# StudyGraph Frontend

This directory will contain the user-facing web application for StudyGraph.

## Tech Stack (from DECISIONS.md)
- **Framework:** React with Vite (Decision D01)
- **Styling & UI Kit:** Tailwind CSS + shadcn/ui (Decision D02)
- **Graph Visualization:** react-force-graph (2D / 3D) (Decision D03)
- **Testing:** Vitest (Decision D14)

## Architecture Overview
- `src/components/`: Reusable UI elements (cards, buttons, modal dialogs).
- `src/features/graph/`: 2D and 3D knowledge graph canvases.
- `src/features/theory/`: Theory card views and cross-module link chips.
- `src/features/chat/`: Grounded AI study assistant interface.
- `src/features/upload/`: File drop zone and pipeline progress tracker.

The full frontend skeleton will be initialized during the frontend implementation tasks.

