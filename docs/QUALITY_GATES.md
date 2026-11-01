# Quality Gates

Tests that must pass before the demo. Never change a target just to pass.

| ID | Gate | Risk | Direction | Target |
|---|---|---|---|---|
| G01 | Link precision: of 50 hand-labelled links, share a faculty/senior agrees with | R03 | >= | 0.85 |
| G02 | Share of links that have a reason and two source snippets | R03 | >= | 1 |
| G03 | Topic accuracy after review step on 10 real scanned pages | R06 | >= | 0.8 |
| G04 | Chatbot answers with correct citation (20 in-notes questions) | R10 | >= | 0.9 |
| G05 | Out-of-notes questions correctly flagged 'not in your notes' (10 questions) | R10 | >= | 0.9 |
| G06 | Duplicate topics remaining per 100 topics | R08 | <= | 5 |
| G07 | Seconds to process one new 20-page PDF (incremental update) | R07 | <= | 90 |
| G08 | 3D graph frames per second on weakest test device (300 visible nodes) | R14 | >= | 30 |
| G09 | Cross-subject links in demo that a faculty member agrees with (count) | R19 | >= | 3 |
| G10 | Successful offline demo runs out of 3 | R17 | >= | 3 |
