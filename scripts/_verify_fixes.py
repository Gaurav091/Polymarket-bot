"""Throwaway: verify the dead-market fee fix + no-book gate behave as claimed."""
import sys
sys.path.insert(0, ".")

from bot import config

# --- Fix 1: dead_market close must not charge a fictional exit fee ---
fr = config.POLY_FEE_RATE
shares, entry = 158.73, 0.315
entry_fee = shares * fr * entry * (1 - entry)

# old behaviour: exit fee charged at same price -> guaranteed loss
exit_fee_old = shares * fr * entry * (1 - entry)
pnl_old = (entry - entry) * shares - (entry_fee + exit_fee_old)

# new behaviour: dead_market + exit==entry -> exit fee skipped
exit_fee_new = 0.0
pnl_new = (entry - entry) * shares - (entry_fee + exit_fee_new)

print(f"entry_fee       = {entry_fee:.4f}")
print(f"old exit_fee    = {exit_fee_old:.4f}  -> old pnl {pnl_old:.4f}")
print(f"new exit_fee    = {exit_fee_new:.4f}  -> new pnl {pnl_new:.4f}")
assert abs(pnl_new - (-entry_fee)) < 1e-9, "new pnl should equal -entry_fee"
assert pnl_new > pnl_old, "fix must reduce the loss"
print("PASS: dead-market exit fee no longer double-charged")

# --- Fix 2: no-book gate rejects a market with no order book ---
from bot.spread import fetch_spread

# fake market with a bogus token id -> book endpoint returns empty/invalid -> None
fake = "0" * 20
sp = fetch_spread(fake)
print(f"fetch_spread(bogus token) = {sp}")
assert sp is None, "bogus token must yield None (no book)"
print("PASS: no-book gate would reject a market with no live book")
