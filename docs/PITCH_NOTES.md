# StudyGraph — 5-Minute Presentation Pitch Notes & Speaker Script

> **Role & Tone:** Demo-Reliability Guide. Confident, student-relatable, structured, and calm.  
> **Target Time:** 4 minutes 45 seconds (leaves 15 seconds buffer for transitions or questions).  
> **Key Differentiator (Risk R01):** *"NotebookLM answers questions about your files. StudyGraph shows how your whole semester connects."*

---

## The 5-Minute Timed Walkthrough

### 1. The Hook (0:00 – 0:30)
* **What to show on screen:** Your desktop or file folder showing 30+ separate PDF lectures, scans, and slides scattered across folders.
* **What to say:**
  > *"Every semester, students drown in thirty to fifty disconnected files—PDF slides, scanned handwritten notes, syllabus PDFs, and previous-year exam papers. We study each topic in isolation, pass the midterms, and forget everything.*
  > 
  > *Existing AI tools like NotebookLM let you chat with a file, but **NotebookLM answers questions about your files. StudyGraph shows how your whole semester connects**."*

---

### 2. The Subject Graph: Clusters & Drone Shot (0:30 – 1:15)
* **What to do on screen:** Click the **Subject Graph** tab. Point out the colored clusters (Louvain community detection). Click on a cluster to zoom smoothly into its sub-graph.
* **What to say:**
  > *"Instead of an endless folder list, StudyGraph organizes your lectures into an evolving knowledge graph. These colors aren't random—our backend applies Louvain community clustering to detect how topics group naturally.*
  > 
  > *Watch what happens when I click the 'Transport Layer' cluster: the camera zooms smoothly from a high-level drone shot right into the specific concepts like TCP, Flow Control, and Congestion Control."*

---

### 3. The Evolving Graph: November Links to January (1:15 – 2:00)
* **What to do on screen:** Switch to **Upload & Ingest** tab. Upload `demo_upload_sample.txt` (or your pre-cached November note). Watch the graph update.
* **What to say:**
  > *"Knowledge isn't static—it evolves as the semester progresses. In November, our professor covers TLS 1.3 encryption. In ordinary study methods, that note sits in a separate folder.*
  > 
  > *When I upload this November lecture, StudyGraph doesn't re-index everything. It incrementally embeds only the new concepts and discovers nearest neighbors. Look right here: a new knowledge bridge instantly forms connecting this November TLS topic back to our January TCP 3-Way Handshake."*

---

### 4. Verified Link Evidence & User Edits are Sacred (2:00 – 2:45)
* **What to do on screen:** Click the newly formed link. Show the side panel with **Relationship Type**, **Reason**, **Industry Example**, and **Two Verbatim Snippets**. Click **Delete** or **Edit** on a link to show the **Locked** badge.
* **What to say:**
  > *"Rule number one in StudyGraph: **No evidence, no link**. We never allow the AI to hallucinate connections. Every single link must provide a strength rating from 1 to 5, an industry engineering example, and exact source quotes from both documents.*
  > 
  > *And if a student disagrees or our professor explains a concept differently? User edits are sacred. I can delete or edit any link, and the system permanently locks that decision so subsequent uploads never overwrite your corrections."*

---

### 5. Cross-Subject 3D Knowledge Bridges (2:45 – 3:30)
* **What to do on screen:** Switch to **Cross-Subject 3D** tab. Rotate the 3D galaxy space using orbit controls. Highlight a link between Computer Networks and Operating Systems.
* **What to say:**
  > *"Here is the biggest 'aha' moment for any engineering student: the Cross-Subject 3D Graph. Real engineering doesn't stop at subject boundaries.*
  > 
  > *Look at this bridge between Computer Networks and Operating Systems. A network socket in CN directly connects to Process Synchronization and File Descriptors in OS. Clicking the link reveals verified citations from both classes. If your laptop GPU is under heavy load, the system automatically falls back to 2D to guarantee 60 FPS."*

---

### 6. Grounded Study Chat & Honest Fallbacks (3:30 – 4:15)
* **What to do on screen:** Switch to **Study Chat** tab.
  1. Ask: *"How does the TCP 3-way handshake establish a connection?"* -> Show answer with clickable page citation.
  2. Ask: *"How does Shor's quantum algorithm factor large integers?"* -> Show the honest *"Not found in your notes"* banner with labeled general-knowledge fallback.
* **What to say:**
  > *"When exams approach, students need answers they can trust. When I ask about the TCP handshake, StudyGraph cites the exact slide file and page number. Clicking the citation displays the verbatim source text.*
  > 
  > *Even more important is honesty. When I ask an out-of-syllabus question like Shor's quantum algorithm, ordinary LLMs bluff. StudyGraph strictly refuses to fabricate: it states **'Not found in your notes'** first, and then provides a clearly labeled general-knowledge answer."*

---

### 7. Exam Passing Package (4:15 – 4:45)
* **What to do on screen:** Switch to **Exam Mode** tab. Show **Important Concepts (by graph importance)** and **Repeated Questions (from uploaded papers)**. Toggle between 2-mark, 5-mark, and 10-mark answers.
* **What to say:**
  > *"Finally, we built the student passing package: Exam Mode. We combine two objective signals:*
  > *1. Graph Importance: Concepts with the highest centrality in your semester notes.*
  > *2. Real Paper Questions: Extracted from actual university previous-year papers.*
  > 
  > *A student can review repeated questions and instantly generate answers structured specifically for 2-mark definitions, 5-mark explanations, or 10-mark essay answers with diagrams."*

---

### 8. Conclusion & Roadmap (4:45 – 5:00)
* **What to say:**
  > *"StudyGraph transforms isolated semester files into an active, verified knowledge network that stays with you throughout your engineering degree. Thank you, and I welcome your questions!"*

---

## Demo-Reliability Emergency Playbook: What to Say If Something Breaks Live

| Scenario | What happened | What to do & say |
|---|---|---|
| **Venue Wi-Fi Disconnects** | The presentation room internet dies or blocks port 8000. | **Stay calm.** Double-click `start_demo_offline.bat`. All graphs, search, citations, and exam answers run 100% locally from your frozen real snapshot. Say: *"We designed StudyGraph local-first because student dorms and exam halls have notoriously spotty Wi-Fi. Notice that the entire knowledge graph and citations engine run completely offline on my machine."* |
| **API Latency / Throttling** | Live upload or chat takes more than 5 seconds. | Use the pre-cached demo file (`demo_upload_sample.txt`). Say: *"Because large PDFs can take time on free API tiers, our background worker caches intermediate embeddings and delta graphs so the interface remains silky smooth for students."* |
| **Projector Glitch / Laptop Hang** | Laptop crashes or display freezes. | Pull up your 3-minute screen recording on your phone or backup USB drive. Say: *"While the HDMI projector reconnects, let me show you this 3-minute screen capture recorded during our verified offline test run."* |
| **Judges Ask: 'Is this just RAG / NotebookLM?'** | Classic tough judge question. | Quote the core pitch line: *"RAG only looks up text chunks when you ask a question. StudyGraph extracts topics, builds an evolving graph over months, enforces verified two-sided evidence on every link, links across different subjects in 3D, and aligns with syllabus exam structures. It's a semester knowledge engine, not just a search bar."* |

