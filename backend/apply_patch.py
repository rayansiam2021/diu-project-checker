"""
Run this ONCE in your backend/ folder to patch plagiarism.py:
    python apply_patch.py
"""
import sys, os
sys.path.insert(0, '.')

F = os.path.join(os.path.dirname(__file__), '..', 'services', 'plagiarism.py')
F = os.path.abspath(F)

if not os.path.exists(F):
    F = 'services/plagiarism.py'

content = open(F).read()
original = content

content = content.replace(
    "from services.quota_tracker import get_active_key, record_queries",
    "from services.quota_tracker import get_active_pair, record_queries"
)
content = content.replace(
    "from config import GOOGLE_CX, GOOGLE_API_KEYS",
    "from config import GOOGLE_KEY_CX_PAIRS"
)
content = content.replace(
    "    if not GOOGLE_API_KEYS or not GOOGLE_CX:\n        return _scholar_search(query)",
    "    if not GOOGLE_KEY_CX_PAIRS:\n        return _scholar_search(query)"
)
content = content.replace(
    "    key_idx, api_key = get_active_key()",
    "    key_idx, api_key, cx = get_active_pair()"
)
content = content.replace(
    '        params = {"key": api_key, "cx": GOOGLE_CX, "q": p["q"], "num": num}',
    '        params = {"key": api_key, "cx": cx, "q": p["q"], "num": num}'
)

if content == original:
    print("WARNING: No changes made - plagiarism.py may already be patched or has different content")
else:
    open(F, 'w').write(content)
    print("SUCCESS: plagiarism.py patched")
    print("  - Now uses get_active_pair() for key+CX rotation")
    print("  - Each pair uses its own CX")
