"""Verify paper trading PnL — are the profits real?"""
import sqlite3

conn = sqlite3.connect("data/trades.db")
conn.row_factory = sqlite3.Row

# Get the exact trades the user pasted
rows = conn.execute("""
    SELECT id, market_question, side, entry_price, exit_price, amount_usd, shares,
           exit_reason, pnl_usd, edge, signal_source, entry_at, status
    FROM trades WHERE id IN (326,327,328,329,330,331,332,333,334)
    ORDER BY id DESC
""").fetchall()

print("=== USER'S TRADES VERIFIED ===\n")
for r in rows:
    ep = r["entry_price"] or 0
    xp = r["exit_price"] or 0
    shares = r["shares"] or 0
    pnl = r["pnl_usd"] or 0
    bet = r["amount_usd"] or 0
    side = r["side"]
    
    # Simple spread calc for display (exit_yes - entry_yes) * shares
    calc = (xp - ep) * shares
    
    print(f"#{r['id']:3d} | {side:3s} | entry={ep:.3f} exit={xp:.3f} | shares={shares:.1f} | bet=${bet:.2f}")
    print(f"      | reason={r['exit_reason']} | DB PnL=${pnl:+.2f} | math={(xp-ep):+.3f}/share * {shares:.1f} shares = ${calc:+.2f}")
    print()

# Critical question: dead_market closes at entry_price?
print("\n=== DEAD MARKET EXIT LOGIC CHECK ===")
print("If dead_market closes at entry_price, exit_price == entry_price, PnL = $0")
print("But we see non-zero PnL on dead_market exits. Why?\n")

dm = conn.execute("""
    SELECT id, side, entry_price, exit_price, pnl_usd, shares
    FROM trades WHERE exit_reason='dead_market' AND pnl_usd != 0
    ORDER BY id DESC LIMIT 10
""").fetchall()
for r in dm:
    ep = r["entry_price"] or 0
    xp = r["exit_price"] or 0
    diff = xp - ep
    print(f"  #{r['id']} {r['side']} entry={ep:.3f} exit={xp:.3f} diff={diff:+.3f} pnl=${r['pnl_usd']:+.2f} shares={r['shares']:.1f}")

# Check: are the LCK profits from the market actually resolving YES?
print("\n=== LCK MARKET — DID IT RESOLVE? ===")
lck = conn.execute("""
    SELECT id, side, entry_price, exit_price, pnl_usd, exit_reason, entry_at, shares
    FROM trades WHERE market_question LIKE '%LCK%' ORDER BY id
""").fetchall()
print(f"Total LCK trades: {len(lck)}")
total_pnl = sum(r["pnl_usd"] or 0 for r in lck)
print(f"Total LCK PnL: ${total_pnl:+.2f}")
for r in lck:
    ep = r["entry_price"] or 0
    xp = r["exit_price"] or 0
    print(f"  #{r['id']:3d} {r['side']} @ {ep:.3f} -> {xp:.3f} | pnl=${r['pnl_usd']:+.2f} | {r['exit_reason']}")

# The key question: does the bot hold the same position multiple times?
print("\n=== OPEN POSITIONS CHECK ===")
open_trades = conn.execute("""
    SELECT id, market_question, side, entry_price, entry_at
    FROM trades WHERE status='open'
    ORDER BY entry_at
""").fetchall()
for r in open_trades:
    print(f"  #{r['id']} {r['side']} @ {r['entry_price']:.3f} | {r['market_question'][:60]}")

# How is exit_price set for dead_market?
print("\n=== CLOSE_POSITION CODE CHECK ===")
print("dead_market calls close_position(row['id'], row['entry_price'], 'dead_market')")
print("So exit_price = entry_price for dead_market.")
print("This means dead_market PnL should ALWAYS be $0 (exit at entry).")
print("If DB shows non-zero PnL on dead_market, the close_position function")
print("is using a DIFFERENT exit price than what's passed.\n")

# Check close_position function
print("=== ACTUAL close_position PnL calculation ===")
# The close_position function computes:
#   exit_held_price = exit_yes_price if side == "YES" else 1.0 - exit_yes_price
#   pnl = (exit_held_price - entry) * shares
# For dead_market: exit_yes_price = entry_price (passed as row['entry_price'])
# For NO side: exit_held_price = 1.0 - entry_price
# So: pnl = (1.0 - entry_price - entry_price) * shares = (1.0 - 2*entry_price) * shares
# THAT'S THE BUG! Dead market closes at entry_price but the journal treats it as YES price
for r in lck:
    ep = r["entry_price"] or 0
    xp = r["exit_price"] or 0
    shares = r["shares"] or 0
    # If close_position received entry_price as exit_yes_price:
    # For NO side: exit_held = 1.0 - exit_yes_price = 1.0 - entry_price
    # pnl = (1.0 - ep - ep) * shares = (1.0 - 2*ep) * shares
    bug_pnl = (1.0 - 2*ep) * shares
    print(f"  #{r['id']} entry={ep:.3f} shares={shares:.1f} | if exit_yes=entry: pnl = (1-{ep:.3f}-{ep:.3f})*{shares:.1f} = ${bug_pnl:+.2f} | actual=${r['pnl_usd']:+.2f}")

conn.close()
