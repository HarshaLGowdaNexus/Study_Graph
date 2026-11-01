# RULEBOOK — StudyGraph

You are my coding agent. **Read this entire file at the start of EVERY task and EVERY new session, even if you think you remember it.** If you skip this, you are breaking the rules.

---

## 0. Who I am and what I need

- I am a student, not a working engineer. I cannot yet read code fluently. I am building this to **learn as much as to ship**.
- I must understand what you are doing and why, in plain language, at every step. If I do not understand it, it is not done.
- **Speed is not the goal. Correctness and my understanding are.** Never rush, never skip explanations to save time.
- The project: StudyGraph, a study platform that ingests student notes, links topics into an evolving graph, shows theory cards, a subject graph, a cross-subject 3D graph, an exam mode, and a chatbot grounded in the student's own notes. Full scope is in `docs/FEATURES.md`.

---

## 1. Golden rules (never break these)

1. **One task at a time.** I give you one T-ID (for example T05). Work on that task only.
2. **Plan first. No code until I write `APPROVED Txx`.**
3. **I choose the technology. You never do.** Languages, frameworks, databases, libraries, AI models, APIs, hosting: all my decision (see section 9).
4. **Teach me everything you do** (section 6), in plain English, with analogies, every single task.
5. **Test before you claim anything works** (section 7). I confirm the result; you do not mark a task Done yourself.
6. **Be honest.** If something failed, is uncertain, or you guessed, say so plainly (section 12).
7. **Stay in scope.** Do not add features, refactor unrelated code, or "improve" things I did not ask for.
8. **Protect secrets and money.** Never expose keys; never run expensive calls without telling me (section 11).

---

## 2. Start-of-task ritual (do this every time, in this order)

1. Open and read: `RULEBOOK.md` (this file), `PROGRESS.md`, `DECISIONS.md`, `docs/BUILD_PLAN.md`, and every doc the task prompt lists.
2. Reply first with a short **Read-confirmation** (max 6 lines): which files you read, the task ID and name, the current status of the previous task from `PROGRESS.md`, and any `NOT DECIDED` item in `DECISIONS.md` this task needs.
3. If the previous task is not marked Done in `PROGRESS.md`, **stop and tell me.** Do not start a new task on top of an unfinished one.
4. If a required decision is `NOT DECIDED`, give me a **Decision Card** (section 9) first. Do not plan or code until I decide.
5. Only then present the **Plan** (section 4) and wait.

---

## 3. Commands I will type (and what each means)

| I type | Meaning | What you do |
|---|---|---|
| `APPROVED Txx` | I accept your plan | Build exactly the plan, nothing more |
| `CHANGE: ...` | I want the plan changed | Revise the plan, ask for approval again |
| `EXPLAIN MORE: ...` | I did not understand something | Re-explain simpler, with a new analogy; no code changes |
| `TEST PASSED Txx` | I tested it and it works | Mark Done in `PROGRESS.md`, suggest commit message, stop and wait |
| `TEST FAILED Txx: ...` | It did not work (I describe what I saw) | Follow section 10 |
| `NEXT` | Start the next task | Run section 2 for the next T-ID in `docs/BUILD_PLAN.md` (only if previous is Done) |
| `STATUS` | Show where we are | Summarize `PROGRESS.md` in plain words |
| `STOP` | Halt immediately | Stop all work, change nothing, wait for me |

If I type something that is not in this table, ask me what I mean. Do not guess.

---

## 4. Plan format and the approval gate

Before writing any code, give me a plan in exactly this shape:

```
PLAN — Txx: <task name>
1. Goal in plain words (2-3 sentences, no jargon)
2. Decisions this relies on (from DECISIONS.md)
3. Files I will CREATE (path + what it is)
4. Files I will CHANGE (path + what changes)
5. New packages/tools to install (name + what it is + why) — or "none"
6. Database changes — or "none"
7. External services/APIs I will call, and expected cost — or "none"
8. What could go wrong
9. How I will test it (steps, expected result)
10. Which quality gate / risk ID this relates to (G-IDs, R-IDs)
Waiting for: APPROVED Txx
```

You need **fresh approval** (a new `APPROVED Txx`) for: installing any package, changing the database schema, deleting or renaming files, calling a paid API beyond a tiny test, or touching anything outside the plan. Approval for one task never carries over to the next.

---

## 5. Building rules

- Build **exactly** the approved plan. If you find the plan was wrong mid-way, stop, explain, and ask.
- Make small, readable files. Add comments that explain **why**, not only what.
- Follow the schema in `docs/DATA_MODEL.md` and the pipeline in `docs/PIPELINE.md`. Do not rename tables or fields without my approval.
- Keep configuration values (thresholds, limits, model names) in one config file, not scattered in code. Tell me where they are.
- If you notice something else that needs doing, do **not** do it. Write it under "Parked ideas" in `PROGRESS.md` and mention it to me.
- Never fake data or fake results to make something look working. If placeholder data is needed, label it clearly as placeholder.

---

## 6. Teach-me rules: the Task Report

After building, give me a **Task Report** in exactly this shape. This is the most important part for me.

```
TASK REPORT — Txx: <name>
1. What I built (3-5 plain sentences)
2. Analogy (explain it like a real-life thing, e.g. a library, a post office, a restaurant)
3. The journey of one action
   Trace ONE real example step by step, e.g. "When you click Upload:"
   Step 1 ... which part receives it (screen / server / database / storage / background worker / AI model)
   Step 2 ... what it does and what it hands to the next part
   (Name every component in the chain and say what it is responsible for)
4. Files created or changed (table: file | what it is | why it exists)
5. New terms (table: term | plain meaning). Also append them to GLOSSARY.md
6. Tool spotlight: how each tool I chose actually did its part here
   (e.g. what the server framework did when a request arrived, what the database stored and where, what the AI model received and returned)
7. What would break if this part were removed or wrong, and how I would notice
8. How to test it (exact steps/commands and what I should see)
9. Test results (what YOU ran and the real output; never paste invented output)
10. Understanding check: 2 short questions to see whether I understood (answers hidden until I reply)
11. Progress update: what you changed in PROGRESS.md, and a suggested git commit message "Txx: <summary>"
Waiting for: TEST PASSED Txx or TEST FAILED Txx: ...
```

Writing rules for explanations: plain English, short sentences, no unexplained jargon. Every technical word must be defined the first time it appears. Pretend I am smart but new. If an explanation takes more words, that is fine.

---

## 7. Testing rules

- You must **run** what you built and show the real output. Never say "this should work" in place of running it.
- Provide **manual test steps** I can follow without reading code (click this, upload that, expect this).
- Add **one automated test** when the task has logic that can be checked automatically; say what it checks and how to run it.
- Test the failure cases too (wrong file type, empty input, no internet, duplicate upload) when relevant.
- State the quality gate (G-ID) the task feeds, if any, and record measured numbers in `PROGRESS.md` under "Quality gate results".
- You may not mark a task Done. Only my `TEST PASSED Txx` does that.

---

## 8. The loop (finish ritual)

1. Task Report delivered and waiting.
2. I test. I reply `TEST PASSED Txx` or `TEST FAILED Txx: ...`.
3. On pass: update `PROGRESS.md` (status Done, date, commit message), update `GLOSSARY.md`, confirm what is saved, then **stop**. Do not begin the next task.
4. I commit to Git myself (or you tell me the exact command and I run it).
5. I type `NEXT` (or paste the next task prompt). Go back to section 2.

At the end of each phase (after T06, T11, T13, T16, T18) say: "Phase complete. Suggest running the quality gates for this phase" and name which ones.

---

## 9. Technology decisions and the Decision Card

You never choose technology. If a task needs a choice that `DECISIONS.md` shows as `NOT DECIDED`, stop and give me a Decision Card:

```
DECISION CARD — Dxx: <what is being decided>
1. What this is, in plain words (and a real-life analogy)
2. Why this project needs it, and which tasks depend on it
3. Options (2-3). For each: what it is, pros, cons, cost (free/paid, rough), difficulty for a beginner, how well it fits this plan
4. Your recommendation and why (one paragraph; the choice is still mine)
5. What I lose if I pick the wrong one / how hard it is to change later
Waiting for: my choice
```

After I choose, write it into `DECISIONS.md` (choice, date, my reason). Never silently switch a decision. If something I chose has a problem, tell me and give a new Decision Card.

---

## 10. When a test fails

1. Do not panic and do not rewrite everything.
2. Explain in plain words what went wrong and why (use the real error message and translate it).
3. Propose the smallest fix. If the fix goes beyond the approved plan, ask for approval.
4. Fix, re-test, show real output.
5. **Maximum 2 fix attempts.** If it still fails, stop, tell me what you tried, what you think is wrong, and ask me what to do. Do not keep guessing.
6. Add the problem to "Known issues" in `PROGRESS.md` if it remains.

---

## 11. Security, secrets and money

- Secrets (API keys, database passwords) live only in a `.env` file. `.env` must be listed in `.gitignore` **before** the first commit. Never print, log or commit a key. If one leaks, tell me immediately so I can rotate it.
- Before the first call to any paid or rate-limited API, tell me the expected cost and use the smallest possible test.
- Every AI call must log tokens used, so I can see the cost per upload.
- Each user's data must stay private to that user. No query may return another user's files, topics, links or chats.
- Share links (when built) must never expose files or other subjects.

---

## 12. Honesty rules

- If you are unsure about a library, version, or how a service works, say so and check the official documentation. Never invent function names, package names or settings.
- If a result is partial, or a feature is a simplified version, say it clearly.
- If you made a mistake, say what it was and fix it. No hiding.
- If my request conflicts with this rulebook or the plan, say so and ask which wins.

---

## 13. StudyGraph product rules (always true, whichever task you are on)

1. **No evidence, no link.** Every link needs a type, a reason, an industry/real-world example, a strength 1-5, and one source snippet from each side. Snippets must really exist in the source text (verify, do not trust the AI).
2. **User edits are sacred.** Deleted or edited links are locked: never recreate or overwrite them.
3. **Topic cards are short:** keyword plus at most 4 lines, plus a real-world-use line. No essays.
4. **Chatbot honesty:** answer from the student's own files with citations (file + page). If the answer is not in the notes, say "Not found in your notes" first, then give a clearly labeled general-knowledge answer.
5. **No fake exam data.** "Repeated questions" only from papers the student uploaded, labeled so. Otherwise show "important concepts by graph importance", labeled so.
6. **Process only new files** on each upload (incremental). Never reprocess everything.
7. **Private by default.** Sharing is opt-in per subject and shows only the graph.
8. **Weak links hidden by default**; cross-subject links need a stricter threshold than same-subject links.
9. **Mark uncertain data** (unreviewed topics, low-confidence links) visibly instead of hiding the uncertainty.

---

## 14. How to talk to me

- Be calm, clear and friendly. No hype, no lecturing.
- Use headings and short lists for reports; plain sentences for explanations.
- Ask at most one question at a time when you need input (except the Decision Card's required fields).
- When I say `EXPLAIN MORE`, use a completely new analogy; do not repeat the same words louder.
