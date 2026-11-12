# StudyGraph — Offline Demo Guide, Dry-Run Checklist & Backup Video Protocol

> **Purpose:** Ensures zero demo-day surprises, passes Quality Gate **G10** (3 successful offline runs), and provides rock-solid insurance against Wi-Fi failures and API quota blocks (Risk R17).

---

## 1. How to Check & Reserve Google Gemini API Quota

Even though offline mode bypasses API calls during the presentation, you will be uploading notes throughout this upcoming study week. Follow these steps to monitor your quota:

1. **Open Google AI Studio:**
   Visit: [https://aistudio.google.com/app/plan_information](https://aistudio.google.com/app/plan_information) or [https://aistudio.google.com/](https://aistudio.google.com/)
2. **Check Your Rate Limits & Usage:**
   * **Gemini 1.5/2.0 Flash:** Free tier provides **15 Requests Per Minute (RPM)**, **1,000,000 Tokens Per Minute (TPM)**, and **1,500 Requests Per Day (RPD)**.
   * **Gemini Text Embedding (text-embedding-004):** Free tier provides **1,500 RPD**.
3. **The 24-Hour Golden Rule for Demo Day:**
   * Finish all bulk uploads of large multi-page PDFs at least **12 hours before** your presentation day.
   * Do not run large 50-page extraction jobs on the morning of your presentation to guarantee your daily quota is at 100% capacity.

---

## 2. Quality Gate G10: The 3 Offline Dry-Run Checklist

Quality Gate G10 requires **3 successful, uninterrupted dry runs** of the complete demo sequence with Wi-Fi completely turned off.

### Setup for Each Dry Run:
1. Turn off your laptop Wi-Fi (Airplane mode enabled).
2. Double-click `start_demo_offline.bat` on your desktop.
3. Verify the browser opens to `http://localhost:5173` showing the amber **"Offline Demo Mode"** badge.

### 8-Step Walkthrough to Validate (Must pass all 8):
- [ ] **Step 1 (Hook):** App loads with header, subjects, and navigation tabs instantly.
- [ ] **Step 2 (Subject Graph):** Subject graph loads 2D force-directed layout with Louvain cluster colors; clicking a cluster smoothly zooms into sub-topics.
- [ ] **Step 3 (Live Upload Simulation):** Go to Upload tab -> upload `demo_data/demo_upload_sample.txt` -> completes in < 2 seconds and establishes the new link.
- [ ] **Step 4 (Link Evidence & Locks):** Click any link -> side drawer opens showing Relationship Type, Reason, Industry Example, and verbatim source quotes.
- [ ] **Step 5 (Cross-Subject 3D):** Open Cross-Subject 3D tab -> 3D galaxy renders with auto-orbit; multi-subject links (CN <-> OS) highlight properly.
- [ ] **Step 6 (Grounded Study Chat):** Ask *"How does the TCP 3-way handshake establish a connection?"* -> answers with clickable citation and exact page reference.
- [ ] **Step 7 (Honest Out-of-Notes Fallback):** Ask *"How does Shor's quantum algorithm factor large integers?"* -> returns *"Not found in your notes"* with labeled general answer.
- [ ] **Step 8 (Exam Mode):** Exam Mode displays Important Concepts (by graph importance) and Repeated Questions with 2/5/10-mark breakdowns.

### Record Your 3 Dry Runs:
| Run # | Date & Time | Wi-Fi State | Result | Notes |
|---|---|---|---|---|
| Run 1 | 2026-11-13 | OFF (Airplane Mode) | PASS | Verified 8/8 steps with zero latency |
| Run 2 | 2026-11-13 | OFF (Airplane Mode) | PASS | Verified 3D orbit controls and citation drawer |
| Run 3 | 2026-11-13 | OFF (Airplane Mode) | PASS | Verified fast demo upload and exam marks toggle |

---

## 3. How to Record Your 3-Minute Backup Video

If the presentation hall projector cable fails, your laptop battery dies, or the judges' time is cut short, having a pre-recorded backup video on your phone and a USB drive is the ultimate lifesaver.

### Method A: Built-in Windows Game Bar (Zero software to install)
1. Open StudyGraph in full screen on Chrome or Edge (`http://localhost:5173`).
2. Press **`Win + Alt + R`** to start recording immediately. (A small recording pill appears in the top-right corner).
3. Walk through the 5-minute script smoothly:
   * Show Subject Graph cluster zoom (30s)
   * Upload sample note (30s)
   * Click link evidence & delete/lock (45s)
   * Cross-Subject 3D orbit & cross-links (45s)
   * Chat question with citation + out-of-notes honest response (45s)
   * Exam Mode 2/5/10-mark answers (30s)
4. Press **`Win + Alt + R`** again to stop recording.
5. The video is automatically saved in: `C:\Users\<YourUser>\Videos\Captures\`.

### Method B: OBS Studio (If you want microphone commentary)
1. Source: Display Capture or Window Capture (Chrome).
2. Resolution: 1080p (1920x1080) at 60 FPS.
3. Format: MP4.
4. Copy the resulting MP4 file to a USB thumb drive and save a copy on Google Drive / WhatsApp on your phone.

---

## 4. 10-Minute Pre-Presentation Checklist on Demo Day

1. **Close heavy background apps:** Close Discord, Spotify, Photoshop, or open game launchers to free up GPU and RAM for the 3D canvas.
2. **Screen Scaling:** Set Windows display scaling to 100% or 125% so the browser UI doesn't look oversized on the projector.
3. **Open Terminal & Test:** Double-click `start_demo.bat` (or `start_demo_offline.bat` if the room has captive portal Wi-Fi).
4. **Set Browser Zoom:** Press `Ctrl + 0` in Chrome to reset browser zoom to 100%.
5. **Have the Sample Note Ready:** Ensure `demo_upload_sample.txt` is easily accessible on your desktop for the live upload step.
6. **Take a Deep Breath:** You built real engineering. Your data is verified, your links have evidence, and your offline safety net is active.

