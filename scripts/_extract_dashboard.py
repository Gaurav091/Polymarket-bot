"""Extract PAGE constant from dashboard.py to dashboard_page.py."""
import pathlib

p = pathlib.Path("d:/Github repos/Polymarket bot/bot/dashboard.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)

start_idx = 102  # 0-based, line 103: PAGE = """<!DOCTYPE html>
end_idx = 345    # 0-based, line 346: </html>"""

# Create dashboard_page.py
page_lines = lines[start_idx:end_idx + 1]
out = pathlib.Path("d:/Github repos/Polymarket bot/bot/dashboard_page.py")
out.write_text(
    '"""Dashboard HTML template - extracted from dashboard.py."""\n\n'
    + "".join(page_lines)
    + "\n",
    encoding="utf-8",
)
print(f"Created dashboard_page.py: {len(page_lines)} lines")

# Replace PAGE block in dashboard.py with import
new_lines = lines[:start_idx] + ["from .dashboard_page import PAGE\n\n"] + lines[end_idx + 1:]
p.write_text("".join(new_lines), encoding="utf-8")
print(f"dashboard.py: {len(lines)} -> {len(new_lines)} lines")
