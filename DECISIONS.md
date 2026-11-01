# DECISIONS (only I fill this, through you)

Rule: you (the agent) NEVER pick technology. For every row marked NOT DECIDED that a task needs, stop and give me a Decision Card (format in RULEBOOK.md section 9). After I choose, you write my choice here with the date and my reason.

| ID | Decision | Plain meaning | My choice | Date | Why I chose it (my words) |
|---|---|---|---|---|---|
| D01 | Frontend framework | The tool used to build the screens people see in the browser | React with Vite | 2026-11-01 | Chose Option A: React with Vite for clean separation from Python backend, strong ecosystem, and zero SSR issues with 3D canvas |
| D02 | Styling / UI kit | How the screens are styled (colors, buttons, layout) | Tailwind CSS + shadcn/ui | 2026-11-01 | Chose Tailwind CSS + shadcn/ui for modern design, code ownership, built-in accessible dialogs/drawers, and easy styling over 3D canvases |
| D03 | Graph library (2D/3D) | The tool that draws the clickable, zoomable, rotatable graph | react-force-graph (2D/3D) | 2026-11-01 | Chose react-force-graph (2D/3D) because 2D and 3D share the exact same data format, has built-in camera fly-to/zoom, and enables easy 2D fallback |
| D04 | Backend language + framework | The 'brain' server that receives uploads and runs the pipeline | Python with FastAPI | 2026-11-01 | Chose Python with FastAPI for native AI/data science libraries, automatic Swagger docs, async performance, and seamless NetworkX integration |
| D05 | Database (with vector search) | Where topics, links and meaning-vectors are stored | PostgreSQL with pgvector (Supabase) | 2026-11-01 | Chose PostgreSQL with pgvector on Supabase for unified relational + vector data, visual web dashboard, hybrid search queries, and free tier |
| D06 | File storage | Where the original uploaded files are kept | Supabase Storage | 2026-11-01 | Chose Supabase Storage for single-account integration with database, stateless backend deployment, and 1 GB free tier |
| D07 | Background jobs approach | How slow work (reading a 100-page PDF) runs without freezing the app | FastAPI BackgroundTasks | 2026-11-01 | Chose FastAPI BackgroundTasks to avoid Redis/Celery setup complexity, run natively on Windows, and update job progress via Supabase |
| D08 | Vision model for scans/handwriting | The AI that reads images of notes | Google Gemini Flash | 2026-11-01 | Chose Google Gemini Flash for superior handwriting accuracy, generous free tier (1500 RPD), and single API key ecosystem |
| D09 | LLM for topic extraction, link judge and chat | The AI that understands text, finds topics and judges links | Google Gemini Flash | 2026-11-01 | Chose Google Gemini Flash for structured JSON output, fast reasoning, high context window, unified single API key with D08, and free tier |
| D10 | Embeddings model | The AI that turns text into meaning-coordinates so similar ideas sit close together | Google text-embedding-004 | 2026-11-01 | Chose Google text-embedding-004 for optimal 768-dim size (saves DB space), free tier, and single-provider harmony with D08 and D09 |
| D11 | Clustering method | How topics are grouped into clusters for the zoomable graph | NetworkX Louvain Community Detection | 2026-11-01 | Chose NetworkX Louvain Community Detection for pure Python Windows compatibility, automatic community detection, and respecting verified link strengths |
| D12 | Hosting / deployment | Where the app runs for the demo (your laptop or the internet) | Local-first with free cloud deployment (Vercel + Render) | 2026-11-01 | Chose Local-first for fast development and free cloud deployment (Vercel for React, Render for FastAPI) for easy public demos |
| D13 | Login / auth method | How students sign in so their notes stay private | Supabase Auth | 2026-11-01 | Chose Supabase Auth for unified integration with DB/storage, production-grade security without writing crypto, and generous 50k MAU free tier |
| D14 | Testing tools | How automatic tests are written and run | pytest + Vitest | 2026-11-01 | Chose pytest (Backend) + Vitest (Frontend) for fast, reliable unit/integration testing of pipeline logic and React components |
| D15 | PDF / PPT parsing library | The tool that reads text out of PDFs and slides | pdfplumber + pypdf + python-pptx | 2026-11-01 | Chose pdfplumber + pypdf + python-pptx for pure Python Windows simplicity, zero C-binary issues, instant scan detection, and page citation tracking |

## Changes to a decision
If I change a decision later, do not delete the old row. Add a line below describing what changed, what it affects, and which tasks must be revisited.

## Change log
(none yet)
