"""Atomic process/port inspector — writes a readable report to a file so the
results survive the flaky terminal-output plumbing on this host."""
import socket
import struct
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "logs" / "inspect_report.txt"


def listen_port_of(pid: int):
    """Ask netstat-equivalent info via psutil-free trick: use ss/netstat."""

def main():
    lines = []
    lines.append("=== BOT FAMILY PROCESSES ===")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\") | "
             "Where-Object { $_.CommandLine -match 'bot\\.(main|dashboard)' } | "
             "ForEach-Object { '{0}|{1}|{2}' -f $_.ProcessId, $_.ParentProcessId, $_.CommandLine }"],
            capture_output=True, text=True, timeout=30,
        )
        txt = out.stdout.strip()
        lines.append(txt if txt else "(none)")
    except Exception as e:
        lines.append(f"ERR {e}")
    lines.append("\n=== PORT CHECK (common dashboard ports) ===")
    for port in (8450, 8460, 8490, 8520, 8530, 8540, 8610, 8650, 8680):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.4)
        rc = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        if rc == 0:
            lines.append(f"LISTENING on {port}")
    OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
    print("written:", OUT)
