"""Verify PnL calculation for losing trades."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "trades.db"
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

# Check Lake Mead NO trades - the suspicious ones
rows = conn.execute(
    "SELECT id, side, entry_price, exit_price, pnl_usd, shares, amount_usd, "
    "exit_reason FROM trades WHERE market_question LIKE '%Lake Mead%' "
    "AND exit_reason='dead_market'"
).fetchall()
print("=== LAKE MEAD DEAD MARKET TRADES ===")
for r in rows:
    ep = r["entry_price"]
    xp = r["exit_price"]
    pnl = r["pnl_usd"]
    shares = r["shares"]
    side = r["side"]
    # Recalculate
    if side == "NO":
        exit_held = 1.0 - xp
        calc_pnl = (exit_held - ep) * shares
    else:
        exit_held = xp
        calc_pnl = (xp - ep) * shares
    print(f"ID={r['id']} Side={side} Entry={ep:.3f} Exit={xp:.3f} Shares={shares:.1f}")
    print(f"  Stored PnL: ${pnl:+.2f}")
    print(f"  Calculated PnL: ${calc_pnl:+.2f}")
    if side == "NO":
        print(f"  exit_held = 1 - {xp:.3f} = {exit_held:.3f}")
        print(f"  (exit_held - entry) * shares = ({exit_held:.3f} - {ep:.3f}) * {shares:.1f} = {calc_pnl:+.2f}")
    match = "OK" if abs(calc_pnl - pnl) < 0.01 else "MISMATCH!"
    print(f"  Match: {match}")
    print()

# Check a WINNING dead_market trade for comparison
print("\n=== WINNING DEAD MARKET (LCK) FOR COMPARISON ===")
rows2 = conn.execute(
    "SELECT id, side, entry_price, exit_price, pnl_usd, shares, amount_usd, "
    "exit_reason FROM trades WHERE market_question LIKE '%LCK%' "
    "AND exit_reason='dead_market' LIMIT 2"
).fetchall()
for r in rows2:
    ep = r["entry_price"]
    xp = r["exit_price"]
    pnl = r["pnl_usd"]
    shares = r["shares"]
    side = r["side"]
    if side == "NO":
        exit_held = 1.0 - xp
        calc_pnl = (exit_held - ep) * shares
    else:
        exit_held = xp
        calc_pnl = (xp - ep) * shares
    print(f"ID={r['id']} Side={side} Entry={ep:.3f} Exit={xp:.3f} Shares={shares:.1f}")
    print(f"  Stored PnL: ${pnl:+.2f}")
    print(f"  Calculated PnL: ${calc_pnl:+.2f}")
    match = "OK" if abs(calc_pnl - pnl) < 0.01 else "MISMATCH!"
    print(f"  Match: {match}")
    print()

# Check what entry_price actually is - is it the YES price or the side price?
print("\n=== ENTRY PRICE SANITY CHECK ===")
print("Config MIN_ENTRY_PRICE = 0.30 (refers to YES price)")
print("If entry_price stores the SIDE price (NO = 1-YES), then NO entries < 0.70 are valid")
print("If entry_price stores YES price, then NO entries at 0.555 mean YES=0.555")

# Check trade #301 - NC-14 NO @ 0.175 (should be illegal with MIN_ENTRY_PRICE=0.30)
rows3 = conn.execute(
    "SELECT id, side, entry_price, exit_price, pnl_usd, shares, exit_reason "
    "FROM trades WHERE market_question LIKE '%NC-14%' ORDER BY entry_at DESC LIMIT 3"
).fetchall()
print("\n=== NC-14 (entry @ 0.175 with MIN_ENTRY_PRICE=0.30?) ===")
for r in rows3:
    ep = r["entry_price"]
    xp = r["exit_price"]
    side = r["side"]
    pnl = r["pnl_usd"]
    shares = r["shares"]
    if side == "NO":
        exit_held = 1.0 - xp
        calc_pnl = (exit_held - ep) * shares
    else:
        exit_held = xp
        calc_pnl = (xp - ep) * shares
    print(f"  Side={side} Entry={ep:.3f} Exit={xp:.3f} Shares={shares:.1f} Stored: ${pnl:+.2f} Calc: ${calc_pnl:+.2f}")

conn.close()
