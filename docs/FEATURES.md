# Features (from master plan)

Priority: v1 = must work flawlessly | v1.5 = only after v1 passes quality gates | Roadmap = not built now, schema only.

| ID | Module | Feature | Description | Priority | Why it matters (judges / users) | Risks covered | Status |
|---|---|---|---|---|---|---|---|
| F01 | Ingestion | Upload by university > scheme > subject > module folders | Drag-drop PDFs, PPTs, images, scans into subject/module folders. Subject name comes from the folder, then is verified from content. | v1 | Core input; supports any syllabus later | R15 | Not started |
| F02 | Ingestion | Text extraction + vision OCR | Text PDFs read directly; scans and images go through a vision-capable LLM (handles handwriting better than classic OCR). | v1 | Handles real student notes | R06 | Not started |
| F03 | Ingestion | Review extracted topics screen (skippable) | After each upload the student sees extracted topics, can fix or delete wrong ones, or skip. | v1 | Protects graph quality from OCR errors | R06,R03 | Not started |
| F04 | Knowledge | Topic cards: keyword + 1-4 line explanation + real-world use | Each topic gets a keyword, a max 4-line plain explanation, and an industry/real-life application line. | v1 | Fast, happy revision; answers 'why am I learning this' | R04 | Not started |
| F05 | Knowledge | Duplicate topic merge + aliases | Embedding similarity + LLM check merges 'TCP handshake' and '3-way handshake'; student can merge or split manually. | v1 | Keeps graph clean | R08,R09 | Not started |
| F06 | Linking | Link discovery: embedding candidates then LLM judge | Embeddings find candidate pairs (same subject and cross-subject); an LLM judge accepts or rejects each with evidence. | v1 | Main quality differentiator | R03,R19 | Not started |
| F07 | Linking | Link attributes: type, reason, industry example, strength, source snippets | Types: prerequisite_of, same_concept, example_of, applies_in, contrasts_with, part_of. No snippets = no link. | v1 | Explained links vs NotebookLM | R01,R03 | Not started |
| F08 | Linking | Edit / delete / lock links | Student can delete or correct any link; corrected links are locked and never recreated or overwritten. | v1 | Trust + control | R03,R16 | Not started |
| F09 | Linking | Incremental update on new upload | Only the new file is processed and compared against existing topics, even months later; graph version increments. | v1 | Evolving-over-time story; keeps cost low | R07,R16 | Not started |
| F10 | Views | Theory view per subject | Keyword cards grouped by module, with cross-module 'linked to' chips and one-line reasons. | v1 | Concept understanding, not rote | R04 | Not started |
| F11 | Views | Subject graph: clusters, click to zoom into sub-graph | Top level shows main clusters; clicking a node zooms into its sub-graph with short explanations; weak edges hidden by default. | v1 | Cinematic 'drone shot' | R09,R14 | Not started |
| F12 | Views | Cross-subject graph tab (3D, rotate, zoom) | Whole-semester graph with links between subjects, plus a text version of the same links. | v1 | Biggest wow + differentiator | R04,R14,R19 | Not started |
| F13 | Views | Topic search -> focused graph + theory | Type any topic; get its local graph (2-3 hops) and theory card instantly. | v1 | Fast, practical | R09 | Not started |
| F14 | Chat | Chatbot with citations + 'not in your notes' + labeled fallback | Answers from retrieved chunks with file/page citation. If retrieval confidence is low, says so first, then gives a clearly labeled general-knowledge answer. | v1 | Exam usefulness; honest | R10 | Not started |
| F15 | Views | 2D focus mode + automatic performance fallback | Switch to 2D manually or automatically when FPS is low; cap rendered nodes. | v1 | Works on weak laptops/phones | R14 | Not started |
| F16 | Knowledge | Ghost nodes from syllabus (coverage and gaps) | Syllabus topics appear faded and light up when notes cover them; shows uncovered topics. | v1.5 | Graph is never empty; gap finder | R13,R12 | Not started |
| F17 | Ingestion | Notes vs textbook preference per subject | If both exist, student picks which source wins when they conflict; chatbot and theory follow it. | v1.5 | Handles real upload habits | R10 | Not started |
| F18 | Exam | Important concepts list | Ranks topics by graph connectivity and coverage across modules; labeled 'by graph importance'. | v1.5 | Passing-package mode | R05 | Not started |
| F19 | Exam | Repeated questions from uploaded previous-year papers | Parses uploaded papers, clusters similar questions, counts repeats; labeled 'from your uploaded papers'. | v1.5 | Real data only, never fabricated | R05 | Not started |
| F20 | Chat | Marks-based answers (2 / 5 / 10 marks) | Chatbot formats the answer to the chosen marks length using the student's notes. | v1.5 | Direct exam value | R10 | Not started |
| F21 | Views | Guided tour (learning path fly-through) | Auto camera path through a learning path: prerequisite to advanced. | v1.5 | Makes 3D useful, great in demo | R04 | Not started |
| F22 | Safety | Delete-all-my-data + consent text | One button wipes files, topics, links; short consent note on first upload. | v1.5 | Privacy trust | R11 | Not started |
| F23 | Sharing | Per-subject private share link (graph only) | Unguessable, revocable token; shows only that subject's graph, never raw files or other subjects. | Roadmap | Class collaboration | R11 | Not started |
| F24 | Admin | Syllabus versioning + admin update tool | Developer tool to add a new scheme, map old topics to new ones, and migrate graphs without breaking them. | Roadmap | Long-term scalability (every ~4 years) | R12 | Not started |
| F25 | Admin | Multi-university / multi-scheme support | University > scheme > branch > semester > subject hierarchy; built into the schema from day 1. | Roadmap | 'Prepared for every syllabus' | R12 | Not started |
