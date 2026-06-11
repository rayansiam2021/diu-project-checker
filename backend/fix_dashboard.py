"""
Run in the project root: python fix_dashboard.py
Fixes dashboard.html so charts and history don't disappear after upload.
"""
import os, re

F = "frontend/dashboard.html"
if not os.path.exists(F):
    F = os.path.join(os.path.dirname(__file__), "..", "frontend", "dashboard.html")

content = open(F).read()

# Fix: wrap result area so it doesn't overlap the right column
old = '''          <div id="result" class="mt-4 d-none"></div>

          <hr class="my-4">

          <!-- Guidelines populated after analysis -->
          <div id="guidelinesBox"></div>'''

new = '''          <div id="result" class="mt-4 d-none result-shell"></div>

          <div id="guidelinesBox" class="mt-3"></div>

          <hr class="my-4">'''

if old in content:
    content = content.replace(old, new)
    open(F, "w").write(content)
    print("✅ dashboard.html fixed")
else:
    print("⚠️  Pattern not found — dashboard may already be fixed or has different structure")
    print("Manual fix: ensure #result div does not overlap the right column")
