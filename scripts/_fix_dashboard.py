"""Extract PAGE constant from dashboard.py to dashboard_page.py."""
import re, pathlib

p = pathlib.Path("d:/Github repos/Polymarket bot/bot/dashboard.py")
c = p.read_text(encoding="utf-8")
m = re.search(r'PAGE = """(.*?)"""', c, re.DOTALL)
if not m:
    raise SystemExit("PAGE not found")

page_content = m.group(0)  # includes PAGE = """..."""
out = pathlib.Path("d:/Github repos/Polymarket bot/bot/dashboard_page.py")
out.write_text('"""Dashboard HTML template - extracted from dashboard.py."""\n\n' + page_content + "\n", encoding="utf-8")
print(f"Created dashboard_page.py: {page_content.count(chr(10))+1} lines")

# Replace PAGE definition with import in dashboard.py
new_c = c[:m.start()] + 'from .dashboard_page import PAGE\n' + c[m.end():]
p.write_text(new_c, encoding="utf-8")
print(f"dashboard.py: {c.count(chr(10))+1} -> {new_c.count(chr(10))+1} lines")
