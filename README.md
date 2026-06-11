# DIU Project Checker — Complete Setup & Usage Guide

## What This System Does

DIU Project Checker is a web application for Daffodil International University that:

1. **Analyzes** student project reports for plagiarism and AI-generated content
2. **Checks Clearance** — verifies a final year project meets all DIU submission guidelines

---

## System Requirements

| Component | Requirement |
|---|---|
| Python | 3.9 or higher |
| OS | Windows 10/11, Ubuntu, macOS |
| RAM | Minimum 4 GB |
| Internet | Required for Google Search API |

---

## Installation — Step by Step

### Step 1 — Install Python
Download Python 3.11 from https://python.org/downloads  
**Windows:** Check "Add Python to PATH" during install.  
Verify: `python --version`

---

### Step 2 — Install Tesseract OCR
Reads text from scanned pages and Turnitin screenshots.

**Windows:**
1. Download: https://github.com/UB-Mannheim/tesseract/wiki → `tesseract-ocr-w64-setup-5.x.x.exe`
2. Run installer, note the path (`C:\Program Files\Tesseract-OCR\`)
3. Add to PATH: Windows key → "Environment Variables" → User → Path → Edit → New → paste path
4. Open new CMD and verify: `tesseract --version`

**Ubuntu:** `sudo apt install tesseract-ocr`  
**macOS:** `brew install tesseract`

---

### Step 3 — Install Poppler
Converts PDF pages to images for OCR.

**Windows:**
1. Download: https://github.com/oschwartz10612/poppler-windows/releases → latest zip
2. Extract to e.g. `C:\Users\YourName\Downloads\poppler\`
3. Add `...\poppler\poppler-26.x.x\Library\bin` to PATH (same way as Tesseract)
4. Open new CMD and verify: `pdftoppm -v`

**Ubuntu:** `sudo apt install poppler-utils`  
**macOS:** `brew install poppler`

---

### Step 4 — Install Python Dependencies

Open **CMD** (not PowerShell) and run:
```cmd
cd "path\to\diu-checker-fixed-patched\backend"
pip install -r requirements.txt
```

Key packages installed: `fastapi`, `uvicorn`, `PyMuPDF`, `python-docx`, `pdf2image`,
`pytesseract`, `Pillow`, `transformers`, `torch`, `reportlab`, `requests`

---

### Step 5 — Configure API Keys

Edit `backend/.env`:
```
GOOGLE_API_KEY_1=your_google_api_key
GOOGLE_CX_1=your_search_engine_cx
```

Get keys:
- API Key: https://console.cloud.google.com → Enable "Custom Search API" → Credentials
- CX: https://programmablesearchengine.google.com → Create engine → Copy CX

---

### Step 6 — Start the Backend

```cmd
cd "path\to\diu-checker-fixed-patched\backend"
uvicorn main:app --reload --port 8000
```

Expected output:
```
INFO: Uvicorn running on http://127.0.0.1:8000
INFO: ✅ Google Search — Quota: 0/100 used, 100 remaining.
INFO: Application startup complete.
```

---

### Step 7 — Open the Frontend

Double-click `frontend/dashboard.html` or serve it:
```cmd
cd frontend
python -m http.server 5500
```
Then visit: http://127.0.0.1:5500/dashboard.html

---

## Clearance Checker — All 6 Rules Explained

### Rule 1 — Required Sections

These 6 sections **must be present** with a clear heading:

| Section | Keywords Detected |
|---|---|
| Approval | "APPROVAL", "BOARD OF EXAMINERS" |
| Declaration | "DECLARATION", "I hereby declare" |
| Acknowledgement | "ACKNOWLEDGEMENT", "I would like to thank" |
| Abstract | "ABSTRACT", "EXECUTIVE SUMMARY" |
| Table of Contents | "TABLE OF CONTENTS", "CONTENTS" |
| List of Figures | "LIST OF FIGURES" |

> Pages with scanned text (< 80 chars extracted) are automatically OCR'd.

---

### Rule 2 — Signatures

**Approval page** — every named examiner must have a signature above their name:
- Chairman, Internal Examiner(s), External Examiner
- System counts signature lines (underscores, dashes, or OCR'd handwriting)

**Declaration page** — checked separately:
- Supervisor signature must appear above "Supervised By"
- Student signature must appear above "Submitted By"

Result shows: `Approval: 4 sig(s) for 4 person(s) ✓ | Declaration: Supervisor ✓ Student ✓`

---

### Rule 3 — Page Number Format

| Part of Document | Required Format |
|---|---|
| Title page → List of Figures (front matter) | Roman: i, ii, iii, iv… in sequence |
| Chapter 1 onwards (body) | Arabic: 1, 2, 3, 4… in sequence |

System detects chapter start automatically and validates both sections.  
Example output: *"Chapter 1 detected at page 15 — 13 Roman pages, 45 Arabic pages ✓"*

---

### Rule 4 — Turnitin Report Attached

The Turnitin Originality Report must be the **last page(s)** of the PDF.

System looks for: "SIMILARITY INDEX", "ORIGINALITY REPORT", "INTERNET SOURCES", "PRIMARY SOURCES"

If the Turnitin page is a **screenshot or image**, OCR reads it automatically.

---

### Rule 5 — Per-Source Plagiarism Limits

| Source Type | Maximum |
|---|---|
| Internet Sources | ≤ 3% |
| Publications | ≤ 3% |
| Student Papers | ≤ 3% |
| DIU Space (daffodilvarsity, dspace.diu) | ≤ 5% |

System parses each row of the Turnitin source table.  
`<1%` entries are treated as 0.5% (within limits).

---

### Rule 6 — Overall Plagiarism

| Level | Maximum Similarity Index |
|---|---|
| Undergraduate (B.Sc.) | ≤ 35% |
| Graduate (M.Sc., MBA, PhD) | ≤ 25% |

Reads the **SIMILARITY INDEX** number from the top of the Turnitin report.  
Student level is taken from their profile.

---

## How to Use the Clearance Checker

1. Start the backend: `uvicorn main:app --reload --port 8000`
2. Open `dashboard.html` in browser
3. Log in with your account
4. Click the **🎓 Check Clearance** tab
5. Upload your final year project (PDF or DOCX)
   - The file must include the Turnitin report as the last page
6. Click **Check Clearance Eligibility**
7. Wait 30–120 seconds (OCR on scanned pages takes time)
8. Read the result:
   - **✅ ELIGIBLE** — all checks passed
   - **❌ NOT ELIGIBLE** — check "Issues to Fix" and "How to Improve"

---

## Project Structure

```
diu-checker-fixed-patched/
├── backend/
│   ├── main.py                    # FastAPI app, registers all routers
│   ├── database.py                # SQLite models (User, Report)
│   ├── config.py                  # Google API keys from .env
│   ├── requirements.txt           # All Python dependencies
│   ├── quota_usage.json           # Tracks daily API usage per key
│   ├── routers/
│   │   ├── auth.py                # POST /register, POST /login
│   │   ├── users.py               # GET/PUT /users/{id}
│   │   ├── reports.py             # POST /analyze (plagiarism + AI)
│   │   ├── quota.py               # GET /quota/status
│   │   └── clearance.py          # POST /check-clearance
│   └── services/
│       ├── clearance_checker.py   # All 6 clearance rules (main logic)
│       ├── plagiarism.py          # Google Custom Search plagiarism
│       ├── ai_detection.py        # HuggingFace RoBERTa AI detection
│       ├── text_extraction.py     # PDF/DOCX text extraction
│       ├── pdf_report.py          # PDF report generation
│       └── quota_tracker.py       # API key rotation, daily limits
├── frontend/
│   ├── dashboard.html             # Main page — Analyze + Clearance tabs
│   ├── script.js                  # All JS: API calls, result rendering
│   ├── styles.css                 # Custom CSS
│   ├── login.html                 # Login page
│   ├── signup.html                # Registration page
│   ├── profile.html               # Student profile editor
│   └── history.html               # Report history
└── README.md                      # This file
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `tesseract not found` | Not in PATH | Add `C:\Program Files\Tesseract-OCR` to PATH, open new CMD |
| `pdftoppm not found` | Poppler not in PATH | Add poppler `Library\bin` to PATH, open new CMD |
| `ModuleNotFoundError: fitz` | PyMuPDF missing | `pip install PyMuPDF` |
| `torch` install very slow | Full CUDA version | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| Port 8000 in use | Another process | Use `--port 8001` |
| Wrong Turnitin % extracted | Body text numbers confused with similarity index | Fixed in v10 — anchored to SIMILARITY INDEX header |
| Sections not detected | Scanned pages with no text | Fixed in v10 — OCR on all pages < 80 chars |
| Declaration not checked | Checker only looked at approval | Fixed in v10 — separate supervisor/student signature check |
| Page numbering false positive | Body text roman numerals flagged | Fixed in v10 — only checks footer line (last 3 lines per page) |

---

## API Endpoints

| Method | URL | Description |
|---|---|---|
| POST | `/register` | Create account |
| POST | `/login` | Get auth token |
| GET | `/users/{id}` | Get student profile |
| PUT | `/users/{id}` | Update profile/level |
| POST | `/analyze` | Run plagiarism + AI check |
| POST | `/check-clearance` | Run all 6 clearance checks |
| GET | `/quota/status` | View API quota usage |
| GET | `/history/{id}` | Get past reports |

---

## Version History

| Version | Key Changes |
|---|---|
| v6 | Base project — plagiarism + AI detection, user auth |
| v7 | Added clearance endpoint + dashboard tab |
| v8 | OCR fallback, Turnitin page detection, page numbering |
| v9 | Lowered OCR threshold, improved Turnitin % regex |
| v10 (current) | Anchored % to SIMILARITY INDEX; split Approval/Declaration checks; footer-only page number detection; `<1%` source handling; DIU domain detection; precise result cards |

---

## Technologies

| Layer | Technology | Purpose |
|---|---|---|
| Backend | FastAPI + Uvicorn | REST API |
| Database | SQLite + SQLAlchemy | User & report storage |
| PDF Reading | PyMuPDF (fitz) | Text layer extraction |
| OCR | pytesseract + Tesseract | Scanned page reading |
| PDF→Image | pdf2image + Poppler | OCR preprocessing |
| Word Docs | python-docx | DOCX reading |
| AI Detection | HuggingFace Transformers | RoBERTa AI text classifier |
| Plagiarism | Google Custom Search API | Web similarity check |
| Reports | ReportLab | PDF generation |
| Frontend | HTML + Bootstrap 5 + Vanilla JS | UI |

---

*DIU Project Checker v10 — Daffodil International University*
