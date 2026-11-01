# Technology OPTIONS (not decisions)

These were suggestions in the master plan. NOTHING here is decided. Real decisions live only in DECISIONS.md and are made by me. Never assume a choice from this file.

| Layer | Suggested option | Why suggested | Alternative |
|---|---|---|---|
| UI design | Stitch | Fast screens; export to code | Figma |
| Frontend | React (Vite or Next.js) + Tailwind | Common, well supported by code agents | Vue |
| 3D graph | react-force-graph-3d (three.js) + 2D version of same lib | Ready-made zoom/rotate/click; 2D fallback uses same data | Cytoscape.js for 2D |
| Backend API | FastAPI (Python) | You already used it in your loan project | Node/Express |
| Database | Postgres + pgvector (Supabase) | One DB for relational data, vectors and auth; free tier | SQLite + FAISS for local demo |
| File storage | Supabase Storage | Same account as DB | Cloudinary / S3 |
| Background jobs | FastAPI BackgroundTasks first, RQ/Celery only if needed | Avoid infra before it is needed | Supabase queue |
| LLM (vision, extraction, judge, chat) | Gemini API (vision + text) | Strong vision for handwriting, free tier for building | Claude API for the judge step |
| Embeddings | Gemini embeddings (or any one model, used consistently) | Single provider keeps it simple | Open-source sentence-transformers |
| Clustering | networkx community detection (Louvain) | Pure Python, no extra service | igraph |
| Hosting | Frontend on Netlify/Vercel, backend on Render/Railway | Free tiers, quick deploy | Fly.io |
| Demo safety | Cached graph JSON + local fallback + recorded video | Survives Wi-Fi or API failure | - |
