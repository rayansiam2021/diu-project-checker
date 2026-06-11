"""
Run in backend/: python fix_ui_stability.py
Fixes UI instability - charts and history disappearing after upload.
"""
import os, sys
sys.path.insert(0, '.')

F = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'script.js')
F = os.path.abspath(F)

content = open(F).read()
original = content

# Fix 1: Don't hide progressBars when analyzing starts
content = content.replace(
    "  el(\"progressBars\")?.classList.add(\"d-none\");",
    "  // keep progress bars visible during analysis"
)

# Fix 2: After analysis completes, reload history without destroying the page
old_reload = "    renderGuidelines(data.reasoning?.guidelines);\n    await loadHistoryTableAndTrend();\n    await loadQuotaWidget();"
new_reload  = """    renderGuidelines(data.reasoning?.guidelines);
    // Reload history and quota without disrupting the result display
    setTimeout(async () => {
      await loadHistoryTableAndTrend();
      await loadQuotaWidget();
    }, 500);"""

content = content.replace(old_reload, new_reload)

if content == original:
    print("⚠️  No changes made - patterns may differ")
else:
    open(F, "w").write(content)
    print("✅ script.js fixed - UI stability improved")
