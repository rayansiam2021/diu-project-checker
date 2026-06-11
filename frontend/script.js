// DIU Project Checker — Frontend Controller
// Set BACKEND_URL if your backend runs on a different host/port.
const BACKEND_URL = (window.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// ── Utilities ────────────────────────────────────────────────────────────────

function el(id) { return document.getElementById(id); }

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&",  "&amp;")
    .replaceAll("<",  "&lt;")
    .replaceAll(">",  "&gt;")
    .replaceAll('"',  "&quot;")
    .replaceAll("'",  "&#039;");
}

function showMessage(targetId, html, type = "info") {
  const node = el(targetId);
  if (!node) return;
  const cls = {
    success: "alert-success",
    danger:  "alert-danger",
    warning: "alert-warning",
  }[type] || "alert-info";
  node.innerHTML = `<div class="alert ${cls} mb-2" role="alert">${html}</div>`;
}

function mustBeLoggedIn() {
  const userId = localStorage.getItem("user_id");
  if (!userId) window.location.href = "login.html";
  return userId;
}

// ── Auth: Signup ──────────────────────────────────────────────────────────────

const signupForm = el("signupForm");
if (signupForm) {
  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const student_id = el("student_id").value.trim();
    const name       = el("name").value.trim();
    const department = el("department").value.trim();
    const level      = el("level") ? el("level").value : "Undergraduate";
    const photo      = el("photo") ? el("photo").files[0] : null;
    const password   = el("password").value;
    const confirm    = el("confirm_password").value;

    if (password !== confirm) {
      showMessage("msg", "Passwords do not match.", "danger");
      return;
    }

    const fd = new FormData();
    fd.append("student_id",  student_id);
    fd.append("name",        name);
    fd.append("department",  department);
    fd.append("level",       level);
    fd.append("password",    password);
    if (photo) fd.append("photo", photo);

    try {
      const res  = await fetch(`${BACKEND_URL}/signup`, { method: "POST", body: fd });
      const data = await res.json();
      if (data.success) {
        showMessage("msg", "Account created successfully. Redirecting to login…", "success");
        setTimeout(() => (window.location.href = "login.html"), 1200);
      } else {
        showMessage("msg", data.message || "Signup failed.", "danger");
      }
    } catch {
      showMessage("msg", "Network error. Please try again.", "danger");
    }
  });
}

// ── Auth: Login ───────────────────────────────────────────────────────────────

const loginForm = el("loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData();
    fd.append("student_id", el("student_id").value.trim());
    fd.append("password",   el("password").value);

    try {
      const res  = await fetch(`${BACKEND_URL}/login`, { method: "POST", body: fd });
      const data = await res.json();
      if (data.success) {
        localStorage.setItem("user_id", data.user_id);
        window.location.href = "dashboard.html";
      } else {
        showMessage("msg", data.message || "Login failed.", "danger");
      }
    } catch {
      showMessage("msg", "Network error. Please try again.", "danger");
    }
  });
}

// ── Auth: Logout ──────────────────────────────────────────────────────────────

const logoutBtn = el("logoutBtn");
if (logoutBtn) {
  logoutBtn.addEventListener("click", () => {
    localStorage.removeItem("user_id");
    window.location.href = "login.html";
  });
}

// ── Profile ───────────────────────────────────────────────────────────────────

if (el("profileInfo")) {
  const userId = mustBeLoggedIn();
  (async () => {
    let data = null;
    try {
      const res = await fetch(`${BACKEND_URL}/profile/${userId}`);
      data = await res.json();

      if (el("profilePhoto") && data.photo) {
        el("profilePhoto").src = data.photo;
        el("profilePhoto").style.display = "block";
      }
      if (el("profileName")) el("profileName").textContent = data.name || "";
      if (el("profileMeta")) el("profileMeta").textContent = `${data.student_id || ""} • ${data.department || ""}`;

      el("profileInfo").innerHTML = `
        <div class="row g-3">
          <div class="col-md-6"><div class="p-3 bg-white rounded shadow-sm"><b>Name:</b> ${escapeHtml(data.name || "")}</div></div>
          <div class="col-md-6"><div class="p-3 bg-white rounded shadow-sm"><b>Student ID:</b> ${escapeHtml(data.student_id || "")}</div></div>
          <div class="col-md-6"><div class="p-3 bg-white rounded shadow-sm"><b>Department:</b> ${escapeHtml(data.department || "")}</div></div>
          <div class="col-md-6"><div class="p-3 bg-white rounded shadow-sm"><b>Level:</b> ${escapeHtml(data.level || "")}</div></div>
          <div class="col-md-6"><div class="p-3 bg-white rounded shadow-sm"><b>Signup date:</b> ${escapeHtml(data.signup_date || "")}</div></div>
        </div>
      `;
    } catch {
      // data may be null here if the fetch itself failed — guard against it
      el("profileInfo").innerHTML = `<div class="alert alert-danger">Failed to load profile. Please try again.</div>`;
    }
  })();
}

// Password change form (on profile page)
const pwdForm = el("pwdForm");
if (pwdForm) {
  pwdForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const userId      = mustBeLoggedIn();
    const old_pwd     = el("old_pwd").value;
    const new_pwd     = el("new_pwd").value;
    const confirm_new = el("confirm_new").value;

    if (new_pwd !== confirm_new) {
      showMessage("pwdMsg", "New passwords do not match.", "danger");
      return;
    }

    const fd = new FormData();
    fd.append("user_id",      userId);
    fd.append("old_password", old_pwd);
    fd.append("new_password", new_pwd);

    try {
      const res  = await fetch(`${BACKEND_URL}/update_password`, { method: "POST", body: fd });
      const data = await res.json();
      if (data.success) {
        showMessage("pwdMsg", "Password updated successfully.", "success");
        pwdForm.reset();
      } else {
        showMessage("pwdMsg", data.message || "Update failed.", "danger");
      }
    } catch {
      showMessage("pwdMsg", "Network error. Please try again.", "danger");
    }
  });
}

// ── Dashboard chart state ─────────────────────────────────────────────────────

let currentDonut1 = null;
let currentDonut2 = null;
let trendChart    = null;

// ── Guidelines renderer ───────────────────────────────────────────────────────

function renderGuidelines(guidelines) {
  const box = el("guidelinesBox");
  if (!box || !guidelines?.length) return;

  const pill = (lvl) => ({
    "High Risk": "badge bg-danger",
    "Medium":    "badge bg-warning text-dark",
    "Low":       "badge bg-success",
    "Action":    "badge bg-primary",
  }[lvl] || "badge bg-secondary");

  box.innerHTML = `
    <div class="card turnitin-card p-3 mb-3">
      <div class="d-flex align-items-center justify-content-between">
        <h6 class="mb-0">Rule-based Guidelines (What to fix)</h6>
        <span class="text-muted small">Auto-generated from your scores</span>
      </div>
      <div class="mt-3 d-grid gap-2">
        ${guidelines.map(g => `
          <div class="guideline-row">
            <span class="${pill(g.level)}">${escapeHtml(g.level)}</span>
            <span class="ms-2 fw-semibold">${escapeHtml(g.tag)}:</span>
            <span class="ms-2">${escapeHtml(g.message)}</span>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

// ── Donut charts ──────────────────────────────────────────────────────────────

function renderCurrentCharts(plag, ai) {
  const d1 = el("currentChartPlag");
  const d2 = el("currentChartAI");
  if (!d1 || !d2 || typeof Chart === "undefined") return;

  if (currentDonut1) currentDonut1.destroy();
  if (currentDonut2) currentDonut2.destroy();

  currentDonut1 = new Chart(d1, {
    type: "doughnut",
    data: {
      labels: ["Plagiarism", "Original"],
      datasets: [{ data: [plag, Math.max(0, 100 - plag)], backgroundColor: ["#dc3545", "#198754"] }],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } },
  });

  currentDonut2 = new Chart(d2, {
    type: "doughnut",
    data: {
      labels: ["AI-like", "Human-like"],
      datasets: [{ data: [ai, Math.max(0, 100 - ai)], backgroundColor: ["#0dcaf0", "#198754"] }],
    },
    options: { responsive: true, plugins: { legend: { position: "bottom" } } },
  });
}

// ── History table + trend chart ───────────────────────────────────────────────

async function loadHistoryTableAndTrend() {
  const userId      = mustBeLoggedIn();
  const body        = el("reportsBody");
  const cards       = el("historyCards");
  const chartCanvas = el("trendChart");

  if (!body && !chartCanvas && !cards) return;

  try {
    const res  = await fetch(`${BACKEND_URL}/history/${userId}`);
    const rows = await res.json();

    // History page cards
    if (cards) {
      if (!rows.length) {
        cards.innerHTML = `<div class="text-muted text-center py-4">No reports yet. Upload a document from the Dashboard.</div>`;
      } else {
        cards.innerHTML = rows.slice().reverse().map(r => {
          const plag     = Math.round(r.plagiarism || 0);
          const ai       = Math.round(r.ai || 0);
          const simClass = plag >= 40 ? "sim-high" : plag >= 20 ? "sim-mid" : "sim-low";
          const aiClass  = ai   >= 60 ? "ai-high"  : ai   >= 30 ? "ai-mid"  : "ai-low";
          const timeLabel = r.timestamp ? new Date(r.timestamp).toLocaleString() : "";
          return `
            <div class="card turnitin-card p-3">
              <div class="d-flex align-items-start justify-content-between gap-3">
                <div>
                  <div class="fw-semibold">Report #${r.id}</div>
                  <div class="text-muted small">${escapeHtml(r.filename || "Uploaded Document")}</div>
                  <div class="text-muted small">${timeLabel} • Footer: ${r.footerOk ? "OK" : "Check"} • Prelim: ${r.prelimOk ? "OK" : "Check"}</div>
                  ${r.topSources?.length ? `<div class="mt-2 d-flex flex-wrap gap-2">${r.topSources.slice(0, 3).map((_, i) => `<span class="badge rounded-pill text-bg-light border">Source ${i + 1}</span>`).join("")}</div>` : ""}
                </div>
                <div class="d-flex gap-2">
                  <div class="score-pill ${simClass}"><div class="score-num">${plag}%</div><div class="score-label">Similarity</div></div>
                  <div class="score-pill ${aiClass}"><div class="score-num">${ai}%</div><div class="score-label">AI</div></div>
                </div>
              </div>
              <div class="mt-3">
                <a class="btn btn-sm btn-primary" href="${BACKEND_URL}/report_pdf/${r.id}" target="_blank">Download Turnitin-style PDF</a>
              </div>
            </div>
          `;
        }).join("");
      }
    }

    // Dashboard table (shows last 10)
    if (body) {
      body.innerHTML = rows.slice().reverse().slice(0, 10).map(r => `
        <tr>
          <td>${r.id}</td>
          <td class="text-truncate" style="max-width:120px;" title="${escapeHtml(r.filename || "")}">${escapeHtml(r.filename || "—")}</td>
          <td>${(r.plagiarism ?? 0).toFixed(2)}%</td>
          <td>${(r.ai        ?? 0).toFixed(2)}%</td>
          <td>${r.footerOk ? "✔" : "✖"}</td>
          <td>${r.prelimOk ? "✔" : "✖"}</td>
          <td>${r.timestamp}</td>
          <td><a class="btn btn-sm btn-outline-secondary" href="${BACKEND_URL}/report_pdf/${r.id}" target="_blank">PDF</a></td>
        </tr>
      `).join("");
    }

    // Trend chart
    if (chartCanvas && typeof Chart !== "undefined") {
      const labels   = rows.map(r => `#${r.id}`);
      const plagData = rows.map(r => r.plagiarism ?? 0);
      const aiData   = rows.map(r => r.ai         ?? 0);

      if (trendChart) trendChart.destroy();
      trendChart = new Chart(chartCanvas, {
        type: "line",
        data: {
          labels,
          datasets: [
            { label: "Plagiarism %", data: plagData, tension: 0.25, borderColor: "#dc3545", backgroundColor: "rgba(220,53,69,.1)" },
            { label: "AI %",         data: aiData,   tension: 0.25, borderColor: "#0dcaf0", backgroundColor: "rgba(13,202,240,.1)" },
          ],
        },
        options: { responsive: true, plugins: { legend: { position: "bottom" } } },
      });
    }
  } catch {
    if (cards) cards.innerHTML = `<div class="alert alert-danger">Failed to load history.</div>`;
  }
}

// ── Report submission ─────────────────────────────────────────────────────────

async function handleReportSubmit(e) {
  e.preventDefault();
  const userId    = mustBeLoggedIn();
  const fileInput = el("reportFile");
  const analyzing = el("analyzing");
  const resultBox = el("result");

  if (!fileInput?.files?.[0]) {
    if (resultBox) { resultBox.classList.remove("d-none"); resultBox.innerHTML = `<div class="alert alert-warning">Please choose a file.</div>`; }
    return;
  }

  if (analyzing) analyzing.classList.remove("d-none");
  if (resultBox) { resultBox.classList.add("d-none"); resultBox.innerHTML = ""; }
  el("progressBars")?.classList.add("d-none");

  const fd = new FormData();
  fd.append("studentId", userId);
  fd.append("report",    fileInput.files[0]);

  try {
    const res  = await fetch(`${BACKEND_URL}/check`, { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || "Analysis failed");

    const plag = Number(data.plagiarism ?? 0);
    const ai   = Number(data.ai         ?? 0);

    // Progress bars
    el("progressBars")?.classList.remove("d-none");
    const plagBar = el("plagBar");
    const aiBar   = el("aiBar");
    if (plagBar) { plagBar.style.width = `${Math.min(100, Math.max(0, plag))}%`; plagBar.textContent = `${plag.toFixed(2)}%`; }
    if (aiBar)   { aiBar.style.width   = `${Math.min(100, Math.max(0, ai))}%`;   aiBar.textContent   = `${ai.toFixed(2)}%`;   }

    // Checks + reasoning
    const checks     = el("checks");
    const r          = data.reasoning || {};
    const recs       = (r.recommendations || []).map(x => `<li>${escapeHtml(x)}</li>`).join("");

    if (checks) {
      const footerText  = data.footerOk ? "Footer detected" : "Footer missing — add DIU footer/department footer";
      const prelimText  = data.prelimOk ? "Preliminary section detected" : "Prelim/Abstract not detected — add preliminary pages";
      const plagHint    = plag < 20 ? "Good: low similarity." : plag < 40 ? "Review citations and paraphrase." : "High similarity: rewrite + cite sources.";
      const aiHint      = ai   < 20 ? "Good: mostly human-like." : ai < 40 ? "Rewrite key parts in your own voice." : "High AI-likeness: add original details + rewrite.";
      const levelLabel  = data.limits?.level || "Undergraduate";
      const limitPlag   = data.limits?.plagiarismLimit ?? 35;
      const limitAI     = data.limits?.aiLimit         ?? 35;
      const plagStatus  = data.status?.plagiarismStatus ?? (plag <= limitPlag ? "OK" : "ABOVE_LIMIT");
      const aiStatus    = data.status?.aiStatus         ?? (ai   <= limitAI   ? "OK" : "ABOVE_LIMIT");

      checks.innerHTML = `
        <div class="mt-2 d-flex flex-wrap gap-2">
          <span class="badge bg-${r.badgeColor || "secondary"}">${escapeHtml(r.badge || "Result")}</span>
          <span class="badge bg-${data.footerOk ? "success" : "secondary"}">Footer</span>
          <span class="badge bg-${data.prelimOk ? "success" : "secondary"}">Prelim</span>
        </div>
        <div class="mt-3 quality-grid">
          <div class="q-item">
            <div class="q-title">Plagiarism</div>
            <div class="q-value">${plag.toFixed(2)}% <span class="ms-1 badge ${plagStatus === "OK" ? "bg-success" : "bg-danger"}">${plagStatus === "OK" ? "Within limit" : "Above limit"}</span></div>
            <div class="q-sub">Safe limit for ${escapeHtml(levelLabel)}: <b>${limitPlag}%</b></div>
            <div class="q-sub">${escapeHtml(plagHint)}</div>
          </div>
          <div class="q-item">
            <div class="q-title">AI Content</div>
            <div class="q-value">${ai.toFixed(2)}% <span class="ms-1 badge ${aiStatus === "OK" ? "bg-success" : "bg-danger"}">${aiStatus === "OK" ? "Within limit" : "Above limit"}</span></div>
            <div class="q-sub">Safe limit for ${escapeHtml(levelLabel)}: <b>${limitAI}%</b></div>
            <div class="q-sub">${escapeHtml(aiHint)}</div>
          </div>
          <div class="q-item">
            <div class="q-title">Format Check</div>
            <div class="q-sub">${escapeHtml(footerText)}</div>
            <div class="q-sub">${escapeHtml(prelimText)}</div>
          </div>
        </div>
        <div class="mt-3">
          <div class="fw-semibold mb-1">Explanation (why this score?)</div>
          <div class="small text-muted">${escapeHtml(r.plagiarismExplanation || "")}</div>
          <div class="small text-muted mt-1">${escapeHtml(r.aiExplanation || "")}</div>
          <div class="fw-semibold mt-2">Recommendations</div>
          <ul class="mb-0 small">${recs}</ul>
        </div>
      `;
    }

    // Full result block
    if (resultBox) {
      resultBox.classList.remove("d-none");

      const plagSents  = (data.highlights?.plagiarismSentences || r.matchExamples || []).slice(0, 8);
      const aiFlags    = (data.highlights?.aiSentences || []).slice(0, 8);
      const sources    = Array.isArray(data.plagSources) ? data.plagSources : [];

      const plagListHtml = plagSents.length
        ? plagSents.map(s => `<li class="hl-item hl-plag"><span class="hl-tag">Plagiarism</span> ${escapeHtml(s)}</li>`).join("")
        : `<li class="text-muted small">No high-confidence matched sentences captured. Still review citations.</li>`;

      const aiListHtml = aiFlags.length
        ? aiFlags.map(o => `<li class="hl-item hl-ai"><span class="hl-tag">AI</span> ${escapeHtml(o.sentence || "")} <span class="badge bg-info text-dark ms-2">${Number(o.aiProb || 0).toFixed(1)}%</span></li>`).join("")
        : `<li class="text-muted small">No strongly AI-like sentences flagged for display.</li>`;

      const sourcesHtml = sources.length
        ? sources.slice(0, 10).map((m, idx) => {
            const items = Array.isArray(m.sources) ? m.sources : [];
            const links = items.slice(0, 3).map(s => `
              <div class="src-item">
                <div class="src-title">• <a href="${escapeHtml(s.link || "")}" target="_blank" rel="noopener">${escapeHtml(s.title || "Source")}</a></div>
                <div class="src-link small text-muted">${escapeHtml(s.link || "")}</div>
                <div class="src-snippet small">${escapeHtml(s.snippet || "")}</div>
              </div>`).join("");
            return `<div class="src-match">
              <div class="fw-semibold small mb-1">Match ${idx + 1}</div>
              <div class="small mb-2"><span class="badge bg-danger me-2">Matched sentence</span>${escapeHtml(m.sentence || m.match || "")}</div>
              ${links || '<div class="text-muted small">No source details returned.</div>'}
            </div>`;
          }).join("")
        : `<div class="text-muted small">No matched web sources recorded.</div>`;

      const fixPlag = plag >= 20 ? "Add citations, rewrite copied lines, and use quotation marks for direct quotes." : "Keep citing sources consistently.";
      const fixAI   = ai   >= 20 ? "Rewrite key sections in your own voice and add more specific, project-based details." : "Your writing style looks mostly human — keep it consistent.";

      resultBox.innerHTML = `
        <div class="result-shell">
          <div class="d-flex flex-wrap gap-2 align-items-center justify-content-between mb-3">
            <div>
              <div class="h5 mb-1">Analysis Complete</div>
              <div class="text-muted small">Report ID: <b>#${data.reportId}</b> • File: <b>${escapeHtml(fileInput.files[0].name)}</b></div>
            </div>
            <div class="d-flex gap-2">
              <a class="btn btn-outline-secondary" target="_blank" href="${BACKEND_URL}/report_pdf/${data.reportId}">📄 Download PDF</a>
              <a class="btn btn-outline-primary" href="history.html">View History</a>
            </div>
          </div>

          <div class="row g-3">
            <div class="col-lg-6">
              <div class="p-3 bg-white rounded shadow-sm">
                <div class="fw-semibold mb-2">Plagiarism Breakdown</div>
                <canvas id="currentChartPlag" height="220"></canvas>
                <div class="small text-muted mt-2">${escapeHtml(fixPlag)}</div>
              </div>
            </div>
            <div class="col-lg-6">
              <div class="p-3 bg-white rounded shadow-sm">
                <div class="fw-semibold mb-2">AI Content Breakdown</div>
                <canvas id="currentChartAI" height="220"></canvas>
                <div class="small text-muted mt-2">${escapeHtml(fixAI)}</div>
              </div>
            </div>
          </div>

          <div class="mt-3 p-3 bg-white rounded shadow-sm">
            <div class="d-flex flex-wrap gap-2 align-items-center justify-content-between">
              <div class="fw-semibold">Learn from your results (highlighted examples)</div>
              <div class="small text-muted">These are samples — not the full document.</div>
            </div>
            <div class="row g-3 mt-1">
              <div class="col-lg-6">
                <div class="learn-card">
                  <div class="learn-title">Potential Plagiarism Sentences</div>
                  <ul class="learn-list">${plagListHtml}</ul>
                  <div class="mt-3">
                    <div class="fw-semibold">Matched sources (web)</div>
                    <div class="small text-muted mb-2">Where similar text may appear online.</div>
                    <div class="sources-box">${sourcesHtml}</div>
                  </div>
                </div>
              </div>
              <div class="col-lg-6">
                <div class="learn-card">
                  <div class="learn-title">Likely AI-Generated Sentences</div>
                  <ul class="learn-list">${aiListHtml}</ul>
                </div>
              </div>
            </div>
            <div class="mt-3">
              <div class="fw-semibold mb-1">Quick checklist</div>
              <div class="row g-2">
                <div class="col-md-6"><div class="tip-item"><div class="tip-title">Plagiarism</div><div class="tip-text">Cite sources, paraphrase properly, and avoid copying long lines.</div></div></div>
                <div class="col-md-6"><div class="tip-item"><div class="tip-title">AI Content</div><div class="tip-text">Add your own examples, numbers, screenshots, and methodology details.</div></div></div>
              </div>
            </div>
          </div>
        </div>
      `;
    }

    renderCurrentCharts(plag, ai);
    renderGuidelines(data.reasoning?.guidelines);
    await loadHistoryTableAndTrend();

  } catch (err) {
    if (resultBox) {
      resultBox.classList.remove("d-none");
      resultBox.innerHTML = `<div class="alert alert-danger">${escapeHtml(err.message || "Analysis failed.")}</div>`;
    }
  } finally {
    if (analyzing) analyzing.classList.add("d-none");
  }
}

const reportForm = el("reportForm");
if (reportForm) {
  mustBeLoggedIn();
  reportForm.addEventListener("submit", handleReportSubmit);
  loadHistoryTableAndTrend();
}

// ── History page (standalone) ─────────────────────────────────────────────────
// historyCards is populated by loadHistoryTableAndTrend() above,
// which is called when historyCards exists on the page.
if (el("historyCards") && !reportForm) {
  mustBeLoggedIn();
  loadHistoryTableAndTrend();
}


// ── Mode switching ────────────────────────────────────────────────────────────

function switchMode(mode) {
  const isAnalyze = mode === "analyze";
  el("panelAnalyze")?.classList.toggle("d-none", !isAnalyze);
  el("panelClearance")?.classList.toggle("d-none", isAnalyze);
  el("tabAnalyze")?.classList.toggle("active", isAnalyze);
  el("tabClearance")?.classList.toggle("active", !isAnalyze);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function badgeHtml(pass) {
  if (pass === true)  return '<span class="check-badge badge-pass">PASS</span>';
  if (pass === false) return '<span class="check-badge badge-fail">FAIL</span>';
  if (pass === null)  return '<span class="check-badge badge-warn">Review</span>';
  return '<span class="check-badge badge-unknown">Unknown</span>';
}

function cardClass(pass) {
  if (pass === true)  return "check-card pass";
  if (pass === false) return "check-card fail";
  if (pass === null)  return "check-card warn";
  return "check-card unknown";
}

// ── Clearance result renderer ─────────────────────────────────────────────────

function renderClearanceResult(data, filename) {
  const box = el("clearanceResult");
  if (!box) return;
  box.classList.remove("d-none");

  const checks  = data.checks || {};
  const eligible = data.eligible;
  const issues   = data.issues || [];
  const warnings = data.warnings || [];

  // ── Banner ──
  const bannerClass = eligible ? "eligible" : "ineligible";
  const bannerIcon  = eligible ? "✅" : "❌";
  const bannerTitle = eligible ? "ELIGIBLE FOR CLEARANCE" : "NOT ELIGIBLE FOR CLEARANCE";
  const bannerSub   = eligible
    ? "All required checks passed. This project meets DIU submission guidelines."
    : `${issues.length} issue(s) must be resolved before submission.`;

  // ── Helper: badge ──
  function badge(pass) {
    if (pass === true)  return '<span class="check-badge badge-pass">PASS</span>';
    if (pass === false) return '<span class="check-badge badge-fail">FAIL</span>';
    if (pass === null)  return '<span class="check-badge badge-warn">Review</span>';
    return '<span class="check-badge badge-unknown">Unknown</span>';
  }
  function cc(pass) {
    if (pass === true)  return "check-card pass";
    if (pass === false) return "check-card fail";
    if (pass === null)  return "check-card warn";
    return "check-card unknown";
  }

  // ── 1. Required Sections card ──
  function requiredSectionsCard() {
    const chk = checks.required_sections || {};
    const sections = chk.sections || {};
    const missing  = chk.missing || [];
    const total    = Object.keys(sections).length || 6;
    const found    = Object.values(sections).filter(Boolean).length;

    const SECTION_LABELS = {
      approval:          "Approval",
      declaration:       "Declaration",
      acknowledgement:   "Acknowledgement",
      abstract:          "Abstract",
      table_of_contents: "Table of Contents",
      list_of_figures:   "List of Figures",
    };

    const rows = Object.entries(SECTION_LABELS).map(([key, label]) => {
      const ok = sections[key] !== false;
      return `
        <div style="display:flex;align-items:center;justify-content:space-between;
                    padding:5px 8px;border-radius:6px;margin-bottom:3px;
                    background:${ok ? '#f0fdf4' : '#fef2f2'};">
          <span style="font-size:12px;color:#374151;">📄 ${escapeHtml(label)}</span>
          <span style="font-size:11px;font-weight:600;color:${ok ? '#059669' : '#dc2626'};">
            ${ok ? '✓ Found' : '✗ Not Found'}
          </span>
        </div>`;
    }).join("");

    return `
      <div class="${cc(chk.pass)}">
        <div class="check-title">
          <span>📋</span> Required Sections ${badge(chk.pass)}
        </div>
        <div style="font-size:12px;color:#6b7280;margin-bottom:8px;">
          ${found} of ${total} required sections found
        </div>
        ${rows}
      </div>`;
  }

  // ── 2. Signatures card ──
  function sigCard() {
    const chk  = checks.approval_signatures || {};
    const apd  = chk.approval_detail || {};
    const decd = chk.declaration_detail || {};
    const pass = chk.pass;
    const personDetails = apd.person_details || [];
    const personsSimple = apd.persons || [];

    // Person rows with sig status
    let personRows = "";
    if (personDetails.length > 0) {
      personRows = personDetails.map(p => {
        const subtitle = [p.title, p.role].filter(Boolean).join(" · ");
        return `
          <div style="display:flex;align-items:flex-start;justify-content:space-between;
                      padding:6px 8px;border-radius:6px;margin-bottom:4px;
                      background:${p.signed ? '#f0fdf4' : '#fef2f2'};border:1px solid ${p.signed ? '#bbf7d0' : '#fecaca'};">
            <div>
              <div style="font-size:12px;font-weight:600;color:#1f2937;">${escapeHtml(p.name)}</div>
              ${subtitle ? `<div style="font-size:11px;color:#6b7280;margin-top:1px;">${escapeHtml(subtitle)}</div>` : ""}
            </div>
            <span style="font-size:11px;font-weight:700;white-space:nowrap;margin-left:8px;
                         color:${p.signed ? '#059669' : '#dc2626'};">
              ${p.signed ? '✍️ Signed' : '⚠ No Sig'}
            </span>
          </div>`;
      }).join("");
    } else if (personsSimple.length > 0) {
      // Fallback to simple list if no details
      personRows = personsSimple.slice(0, 8).map(p => `
        <div style="padding:4px 8px;font-size:12px;color:#374151;background:#f9fafb;
                    border-radius:5px;margin-bottom:3px;">👤 ${escapeHtml(p)}</div>`
      ).join("");
    }

    const approvalBlock = `
      <div style="margin-bottom:10px;">
        <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:5px;
                    padding-bottom:4px;border-bottom:1px solid #e5e7eb;">
          📝 Approval Page
          ${apd.pass === true
            ? `<span style="color:#059669;font-weight:400;margin-left:6px;">✓ ${apd.sig_count||0}/${(apd.person_details||apd.persons||[]).length} signed</span>`
            : `<span style="color:#dc2626;font-weight:400;margin-left:6px;">⚠ Check signatures</span>`}
        </div>
        ${personRows || '<div style="font-size:11px;color:#9ca3af;">No persons detected</div>'}
      </div>`;

    const declBlock = `
      <div>
        <div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:5px;
                    padding-bottom:4px;border-bottom:1px solid #e5e7eb;">
          📝 Declaration Page
        </div>
        <div style="display:flex;gap:10px;">
          <div style="flex:1;padding:6px 8px;border-radius:6px;text-align:center;
                      background:${decd.supervisor_signed ? '#f0fdf4' : '#fef2f2'};
                      border:1px solid ${decd.supervisor_signed ? '#bbf7d0' : '#fecaca'};">
            <div style="font-size:11px;color:#6b7280;">Supervisor</div>
            <div style="font-size:13px;font-weight:700;color:${decd.supervisor_signed ? '#059669' : '#dc2626'};">
              ${decd.supervisor_signed ? '✍️ Signed' : '✗ Missing'}
            </div>
          </div>
          <div style="flex:1;padding:6px 8px;border-radius:6px;text-align:center;
                      background:${decd.student_signed ? '#f0fdf4' : '#fef2f2'};
                      border:1px solid ${decd.student_signed ? '#bbf7d0' : '#fecaca'};">
            <div style="font-size:11px;color:#6b7280;">Student</div>
            <div style="font-size:13px;font-weight:700;color:${decd.student_signed ? '#059669' : '#dc2626'};">
              ${decd.student_signed ? '✍️ Signed' : '✗ Missing'}
            </div>
          </div>
        </div>
      </div>`;

    return `
      <div class="${cc(pass)}">
        <div class="check-title">
          <span>✍️</span> Signatures ${badge(pass)}
        </div>
        ${approvalBlock}
        ${declBlock}
      </div>`;
  }

  // ── 3. Page numbering card ──
  function pageNumCard() {
    const chk = checks.page_numbering || {};
    const romanVals   = chk.front_roman_values || [];
    const arabicVals  = chk.body_arabic_values || [];
    const chapterPage = chk.chapter_starts_at_page;
    const issues      = chk.issues || [];

    const romanDisplay = romanVals.length
      ? romanVals.map(v => `<span style="display:inline-block;padding:1px 6px;margin:1px;background:#eff6ff;
          border:1px solid #bfdbfe;border-radius:4px;font-size:10px;color:#1d4ed8;font-weight:600;">
          ${escapeHtml(String(v).toUpperCase())}</span>`).join("")
      : `<span style="font-size:11px;color:#9ca3af;">None detected</span>`;

    const arabicDisplay = arabicVals.length
      ? arabicVals.map(v => `<span style="display:inline-block;padding:1px 6px;margin:1px;background:#f0fdf4;
          border:1px solid #bbf7d0;border-radius:4px;font-size:10px;color:#15803d;font-weight:600;">
          ${escapeHtml(String(v))}</span>`).join("")
          + (chk.body_arabic_found > 8 ? `<span style="font-size:10px;color:#9ca3af;margin-left:4px;">…+${chk.body_arabic_found-8} more</span>` : "")
      : `<span style="font-size:11px;color:#9ca3af;">None detected</span>`;

    const issueRows = issues.map(i =>
      `<div style="font-size:11px;color:#dc2626;margin-top:3px;display:flex;gap:4px;">
        <span>⚠</span><span>${escapeHtml(i)}</span>
      </div>`
    ).join("");

    return `
      <div class="${cc(chk.pass)}">
        <div class="check-title">
          <span>🔢</span> Page Number Format ${badge(chk.pass)}
        </div>
        <div class="check-msg">${escapeHtml(chk.message || "")}</div>
        ${chapterPage ? `
          <div style="margin-top:8px;padding:5px 8px;background:#f9fafb;border-radius:6px;
                      font-size:12px;color:#374151;border:1px solid #e5e7eb;">
            📖 Chapter 1 starts at <strong>page ${chapterPage}</strong>
          </div>` : ""}
        <div style="margin-top:8px;">
          <div style="font-size:11px;font-weight:600;color:#374151;margin-bottom:4px;">
            Front Matter — Roman Numerals (${chk.front_roman_found ?? 0} pages)
          </div>
          <div style="line-height:1.8;">${romanDisplay}</div>
        </div>
        <div style="margin-top:8px;">
          <div style="font-size:11px;font-weight:600;color:#374151;margin-bottom:4px;">
            Body — Arabic Numerals (${chk.body_arabic_found ?? 0} pages total)
          </div>
          <div style="line-height:1.8;">${arabicDisplay}</div>
        </div>
        ${issueRows}
      </div>`;
  }

  // ── 4. Turnitin source breakdown ──
  const srcData   = checks.turnitin_sources || {};
  const allSources = srcData.sources || [];
  const srcIssues  = srcData.source_issues || [];

  const catSources    = allSources.filter(s => s.type === "category");
  const indivSources  = allSources.filter(s => s.type === "individual");

  let sourcesHtml = "";
  if (allSources.length) {
    // Category totals — informational only, no limit check
    const catRows = catSources.map(s => {
      const pct = s.percentage === 0.5 ? "<1" : s.percentage;
      return `<tr>
        <td style="color:#374151;">${escapeHtml(s.source)}</td>
        <td style="font-weight:600;color:#374151;">${pct}%</td>
        <td style="color:#9ca3af;font-style:italic;">—</td>
        <td style="color:#6b7280;font-size:11px;">Aggregate total</td>
      </tr>`;
    }).join("");

    // Individual source rows — per-source limit applies
    const indivRows = indivSources.map(s => {
      const isDiu = ["diu","daffodil","dspace"].some(d => s.source.toLowerCase().includes(d));
      const limit = isDiu ? 5 : 3;
      const over  = s.percentage > limit;
      const pct   = s.percentage === 0.5 ? "<1" : s.percentage;
      return `<tr style="${over ? 'background:#fef2f2;' : ''}">
        <td>
          ${escapeHtml(s.source)}
          ${isDiu ? '<span style="font-size:10px;background:#dbeafe;color:#1e40af;padding:1px 5px;border-radius:4px;margin-left:4px;">DIU</span>' : ""}
        </td>
        <td class="${over ? 'pct-bad' : 'pct-ok'}">${pct}%</td>
        <td>${limit}%</td>
        <td>${over ? '❌ Exceeds' : '✅ OK'}</td>
      </tr>`;
    }).join("");

    sourcesHtml = `
      <div class="mt-3" style="background:#fff;border:1.5px solid #e5e7eb;border-radius:10px;overflow:hidden;">
        <div style="padding:12px 14px;border-bottom:1px solid #e5e7eb;background:#f9fafb;">
          <div style="font-size:13px;font-weight:700;color:#1f2937;">📊 Turnitin Source Breakdown</div>
          <div style="font-size:11px;color:#6b7280;margin-top:2px;">
            Individual source limit: ≤3% per source &nbsp;|&nbsp; ≤5% for DIU Space sources
          </div>
        </div>

        ${catRows ? `
        <div style="padding:8px 14px;border-bottom:1px solid #f3f4f6;">
          <div style="font-size:11px;font-weight:600;color:#6b7280;letter-spacing:0.5px;
                      text-transform:uppercase;margin-bottom:6px;">
            Overall Category Totals (for reference only — not subject to per-source limits)
          </div>
          <table class="sources-table" style="margin-bottom:0;">
            <thead><tr><th>Category</th><th>%</th><th>Limit</th><th>Note</th></tr></thead>
            <tbody>${catRows}</tbody>
          </table>
        </div>` : ""}

        ${indivRows ? `
        <div style="padding:8px 14px;">
          <div style="font-size:11px;font-weight:600;color:#6b7280;letter-spacing:0.5px;
                      text-transform:uppercase;margin-bottom:6px;">
            Individual Sources (per-source limits apply)
          </div>
          <table class="sources-table" style="margin-bottom:0;">
            <thead><tr><th>Source</th><th>%</th><th>Limit</th><th>Status</th></tr></thead>
            <tbody>${indivRows}</tbody>
          </table>
        </div>` : `
        <div style="padding:12px 14px;font-size:12px;color:#9ca3af;">
          No individual sources parsed from Turnitin report.
        </div>`}
      </div>`;
  }

  // ── 5. Overall plagiarism ──
  const oplag = checks.overall_plagiarism || {};
  const plagColor = oplag.pass === true ? "#059669" : oplag.pass === false ? "#dc2626" : "#d97706";
  const plagHtml = oplag.percentage != null ? `
    <div class="mt-3 p-3" style="background:#fff;border-radius:10px;border:1.5px solid ${plagColor};">
      <div style="font-size:13px;font-weight:700;color:#1f2937;margin-bottom:8px;">📄 Overall Turnitin Similarity</div>
      <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:10px;">
        <span style="font-size:38px;font-weight:800;color:${plagColor};line-height:1;">${oplag.percentage}%</span>
        <span style="font-size:13px;color:#6b7280;">
          Limit for <strong>${escapeHtml(oplag.level || data.level || "")}</strong>:
          <strong>${oplag.limit}%</strong>
          &nbsp;•&nbsp;
          ${oplag.pass
            ? '<span style="color:#059669;font-weight:600;">✅ Within limit</span>'
            : '<span style="color:#dc2626;font-weight:600;">❌ Exceeds limit</span>'}
        </span>
      </div>
      <div style="background:#e5e7eb;border-radius:999px;height:10px;width:100%;overflow:hidden;">
        <div style="background:${plagColor};border-radius:999px;height:10px;
                    width:${Math.min(100,(oplag.percentage/oplag.limit)*100)}%;
                    transition:width 0.6s ease;"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:#9ca3af;margin-top:3px;">
        <span>0%</span><span>Limit: ${oplag.limit}%</span>
      </div>
    </div>` : `
    <div class="mt-3 p-3" style="background:#fffbeb;border-radius:10px;border:1.5px solid #fcd34d;">
      <div style="font-size:13px;font-weight:700;margin-bottom:4px;">📄 Overall Turnitin Similarity</div>
      <div style="font-size:13px;color:#92400e;">⚠️ Could not extract % automatically. Please verify manually from the Turnitin report.</div>
    </div>`;

  // ── 6. Issues & warnings ──
  let issuesHtml = "";
  if (issues.length || warnings.length) {
    const issueItems = issues.map(i =>
      `<li class="issue-item"><span>🔴</span><span>${escapeHtml(i)}</span></li>`
    ).join("");
    const warnItems = warnings.map(w =>
      `<li class="warning-item"><span>⚠️</span><span>${escapeHtml(w)}</span></li>`
    ).join("");
    issuesHtml = `
      <div class="checklist-section">
        ${issues.length ? `
          <div class="improvement-card mb-3">
            <div class="improvement-title">🔴 Issues to Fix Before Submission (${issues.length})</div>
            <ul class="issues-list">${issueItems}</ul>
          </div>` : ""}
        ${warnings.length ? `
          <div class="improvement-card mb-3" style="background:#fffbeb;border-color:#fcd34d;">
            <div class="improvement-title" style="color:#92400e;">⚠️ Requires Manual Review (${warnings.length})</div>
            <ul class="issues-list">${warnItems}</ul>
          </div>` : ""}
      </div>`;
  }

  // ── 7. How to improve ──
  const guideLines = [
    (!checks.required_sections?.pass && checks.required_sections?.missing?.length)
      ? `<li>Add the missing section(s): <strong>${checks.required_sections.missing.join(", ")}</strong>. Each must appear as a clearly labelled heading.</li>` : "",
    (checks.approval_signatures?.approval_detail?.pass === false)
      ? `<li>Approval page: ensure all ${(checks.approval_signatures?.approval_detail?.person_details||checks.approval_signatures?.persons||[]).length} listed persons have physically signed above their name.</li>` : "",
    (checks.approval_signatures?.declaration_detail?.supervisor_signed === false)
      ? `<li>Declaration page: supervisor must sign in the "Supervised By" section.</li>` : "",
    (checks.approval_signatures?.declaration_detail?.student_signed === false)
      ? `<li>Declaration page: student must sign in the "Submitted By" section.</li>` : "",
    (checks.page_numbering?.pass === false)
      ? `<li>Page numbering: use Roman numerals (i, ii, iii…) for all front matter pages. Switch to Arabic numerals (1, 2, 3…) starting at Chapter 1.</li>` : "",
    (!checks.turnitin_attached?.pass)
      ? `<li>Attach the Turnitin Originality Report as the <strong>last page</strong> of your submission.</li>` : "",
    srcIssues.length
      ? `<li>Per-source limit exceeded: ${srcIssues.map(s =>
          `<strong>${escapeHtml(s.source)}</strong> shows ${s.percentage}% (limit: ${s.limit}%)`
        ).join(", ")}. Paraphrase or cite these passages.</li>` : "",
    (checks.overall_plagiarism?.pass === false)
      ? `<li>Overall similarity is <strong>${oplag.percentage}%</strong> — must be below <strong>${oplag.limit}%</strong>. Rewrite copied or AI-generated sections and add proper citations.</li>` : "",
  ].filter(Boolean).join("");

  const guideHtml = guideLines ? `
    <div class="card-section mt-3" style="border-color:#f97316;">
      <div class="fw-bold mb-2" style="color:#c2410c;">📝 How to Improve</div>
      <ol style="font-size:13px;color:#374151;padding-left:18px;line-height:1.8;">${guideLines}</ol>
    </div>` : (eligible ? `
    <div class="card-section mt-3" style="border-color:#059669;background:#f0fdf4;">
      <div class="fw-bold mb-1" style="color:#065f46;">🎉 All checks passed!</div>
      <div style="font-size:13px;color:#374151;">This project meets all DIU submission guidelines and is eligible for clearance.</div>
    </div>` : "");

  // ── Final render ──
  box.innerHTML = `
    <div class="clearance-shell">
      <div style="font-size:13px;color:#6b7280;margin-bottom:12px;">
        📄 <strong>${escapeHtml(filename)}</strong>
        &nbsp;•&nbsp; ${data.total_pages || "?"} pages
        &nbsp;•&nbsp; ${escapeHtml(data.level || "")}
      </div>

      <div class="eligibility-banner ${bannerClass}">
        <div class="eligibility-icon">${bannerIcon}</div>
        <div>
          <div class="eligibility-title">${bannerTitle}</div>
          <div class="eligibility-sub">${escapeHtml(bannerSub)}</div>
        </div>
      </div>

      <div class="check-grid">
        ${requiredSectionsCard()}
        ${sigCard()}
        ${pageNumCard()}
        ${(function checkCard(key, label, icon, extraHtml) {
            const chk = checks[key] || {};
            const pass = chk.pass;
            const _cc = pass === true ? "check-card pass" : pass === false ? "check-card fail" : pass === null ? "check-card warn" : "check-card unknown";
            const _b  = pass === true ? '<span class="check-badge badge-pass">PASS</span>' : pass === false ? '<span class="check-badge badge-fail">FAIL</span>' : pass === null ? '<span class="check-badge badge-warn">Review</span>' : '<span class="check-badge badge-unknown">Unknown</span>';
            return `<div class="${_cc}"><div class="check-title"><span>${icon}</span> ${escapeHtml(label)} ${_b}</div><div class="check-msg">${escapeHtml(chk.message||"")}</div>${extraHtml}</div>`;
          })("turnitin_attached", "Turnitin Attached", "📎",
            checks.turnitin_attached?.pass
              ? `<div style="margin-top:4px;font-size:11px;color:#059669;">Found on page ${checks.turnitin_attached?.message?.match(/\d+/)?.[0] || "?"} ✓</div>`
              : ""
        )}
        ${(function checkCard(key, label, icon, extraHtml) {
            const chk = checks[key] || {};
            const pass = chk.pass;
            const _cc = pass === true ? "check-card pass" : pass === false ? "check-card fail" : pass === null ? "check-card warn" : "check-card unknown";
            const _b  = pass === true ? '<span class="check-badge badge-pass">PASS</span>' : pass === false ? '<span class="check-badge badge-fail">FAIL</span>' : pass === null ? '<span class="check-badge badge-warn">Review</span>' : '<span class="check-badge badge-unknown">Unknown</span>';
            return `<div class="${_cc}"><div class="check-title"><span>${icon}</span> ${escapeHtml(label)} ${_b}</div><div class="check-msg">${escapeHtml(chk.message||"")}</div>${extraHtml}</div>`;
          })("turnitin_sources", "Per-Source Plagiarism", "🔬",
            srcIssues.length
              ? `<div style="margin-top:4px;font-size:11px;color:#dc2626;">${srcIssues.length} source(s) over limit</div>`
              : indivSources.length
                ? `<div style="margin-top:4px;font-size:11px;color:#059669;">All ${indivSources.length} source(s) within limit ✓</div>`
                : ""
        )}
        ${(function checkCard(key, label, icon, extraHtml) {
            const chk = checks[key] || {};
            const pass = chk.pass;
            const _cc = pass === true ? "check-card pass" : pass === false ? "check-card fail" : pass === null ? "check-card warn" : "check-card unknown";
            const _b  = pass === true ? '<span class="check-badge badge-pass">PASS</span>' : pass === false ? '<span class="check-badge badge-fail">FAIL</span>' : pass === null ? '<span class="check-badge badge-warn">Review</span>' : '<span class="check-badge badge-unknown">Unknown</span>';
            return `<div class="${_cc}"><div class="check-title"><span>${icon}</span> ${escapeHtml(label)} ${_b}</div><div class="check-msg">${escapeHtml(chk.message||"")}</div>${extraHtml}</div>`;
          })("overall_plagiarism", "Overall Plagiarism", "📊",
            oplag.percentage != null
              ? `<div style="margin-top:4px;font-size:14px;font-weight:700;color:${plagColor};">${oplag.percentage}% <span style="font-size:11px;font-weight:400;color:#6b7280;">(limit ${oplag.limit}%)</span></div>`
              : ""
        )}
      </div>

      ${sourcesHtml}
      ${plagHtml}
      ${issuesHtml}
      ${guideHtml}
    </div>
  `;
}

// ── Clearance form submission ─────────────────────────────────────────────────

const clearanceForm = el("clearanceForm");
if (clearanceForm) {
  clearanceForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const userId    = mustBeLoggedIn();
    const fileInput = el("clearanceFile");
    const analyzing = el("clearanceAnalyzing");
    const resultBox = el("clearanceResult");

    if (!fileInput?.files?.[0]) {
      if (resultBox) {
        resultBox.classList.remove("d-none");
        resultBox.innerHTML = `<div class="alert alert-warning">Please choose a file to check.</div>`;
      }
      return;
    }

    if (analyzing) analyzing.classList.remove("d-none");
    if (resultBox) { resultBox.classList.add("d-none"); resultBox.innerHTML = ""; }

    const fd = new FormData();
    fd.append("studentId", userId);
    fd.append("report", fileInput.files[0]);

    try {
      const res  = await fetch(`${BACKEND_URL}/check-clearance`, { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || "Clearance check failed");
      renderClearanceResult(data, fileInput.files[0].name);
    } catch (err) {
      if (resultBox) {
        resultBox.classList.remove("d-none");
        resultBox.innerHTML = `<div class="alert alert-danger">${escapeHtml(err.message || "Clearance check failed.")}</div>`;
      }
    } finally {
      if (analyzing) analyzing.classList.add("d-none");
    }
  });
}
