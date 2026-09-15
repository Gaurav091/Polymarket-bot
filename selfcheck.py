"""Quick self-check: survival monitor lifecycle + journal + edge sizing."""
# pyright: reportFloatEquality = false
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Import the SAME module instances the bot uses (bot.* namespace)
import bot.config as config  # noqa: E402

# Speed up the test by shrinking windows
config.SURVIVAL_WINDOW_MINUTES = 30
config.SURVIVAL_GRACE_MINUTES = 0
# Selfcheck tests the death lifecycle — force-enable survival even when
# the bot itself runs with SURVIVAL_ENABLED=false (run-forever mode)
config.SURVIVAL_ENABLED = True

# Use a throwaway DB — never pollute the production journal
config.DB_PATH = str(Path(__file__).parent / "data" / "selfcheck_test.db")

from bot.survival import SurvivalMonitor, VitalState  # noqa: E402

# --- Test 1: boot → arm → alive ---
mon = SurvivalMonitor()
assert mon.check() == VitalState.ALIVE, "grace=0 should arm immediately"
print("PASS: boot → armed → ALIVE")

# --- Test 2: profit resets the clock ---
mon.record_profit(5.0)
assert abs(mon.status.total_realized_profit - 5.0) < 1e-9
assert mon.status.seconds_remaining > 29 * 60
print("PASS: profit resets survival clock")

# --- Test 3: loss does NOT reset the clock ---
before = mon.status.seconds_remaining
time.sleep(0.1)
mon.record_loss(2.0)
assert abs(mon.status.total_realized_loss - 2.0) < 1e-9
assert mon.status.seconds_remaining <= before
print("PASS: loss does not reset clock")

# --- Test 4: death when window elapses ---
mon.status.last_profit_ts = time.time() - (31 * 60)  # simulate 31 min since profit
state = mon.check()
assert state == VitalState.DEAD, f"expected DEAD, got {state}"
print("PASS: bot dies after 30m without profit")

# --- Test 5: critical state before death ---
mon2 = SurvivalMonitor()
mon2.check()
mon2.status.last_profit_ts = time.time() - (28 * 60)  # 2 min left of 30
state = mon2.check()
assert state == VitalState.CRITICAL, f"expected CRITICAL, got {state}"
print("PASS: CRITICAL state at <25% window remaining")

# --- Test 6: journal round-trip ---
from bot import journal  # noqa: E402
journal.init_db()
tid = journal.log_trade_open(
    market_id="test123", question="Test market?", side="YES",
    entry_price=0.50, amount_usd=5.0, shares=10.0, edge=0.2,
    reasoning="test", headline="h", news_source="t", classification="bullish",
    materiality=0.8,
)
pnl = journal.log_trade_close(tid, 0.70, "take_profit")
assert abs(pnl - 2.0) < 0.01, f"expected ~2.0 pnl, got {pnl}"
print(f"PASS: journal round-trip (pnl={pnl:.2f})")

# --- Test 7: edge sizing ---
from bot.edge import size_position  # noqa: E402
s = size_position(0.5)
assert config.MIN_BET_USD <= s <= config.MAX_BET_USD
print(f"PASS: sizing clamps to [{config.MIN_BET_USD}, {config.MAX_BET_USD}] → {s}")

# --- Test 8: regime machine (from poly-maker) ---
from bot.regime import Regime, RegimeTracker  # noqa: E402
rt = RegimeTracker()
assert rt.observe("mkt1", 0.50) == Regime.QUIET
assert rt.observe("mkt1", 0.55) == Regime.QUIET          # small move = quiet
assert rt.observe("mkt1", 0.70) == Regime.EVENT         # 15c jump = event
assert rt.can_trade("mkt1") is False                    # cooloff active
assert rt.observe("mkt2", 1.0) == Regime.HALTED         # resolved market
assert rt.can_trade("mkt3") is True                     # unknown market = tradable
print("PASS: regime machine (EVENT cooloff, HALTED on resolved)")

# --- Test 9: calibration (favorite-longshot bias) ---
from bot.calibration import calibrated_probability, is_resolved  # noqa: E402
assert abs(calibrated_probability(0.5) - 0.5) < 0.03  # mid-range: ≤3pp adjustment (empirical table)
assert calibrated_probability(0.95) < 0.95               # favorite shaded down
assert calibrated_probability(0.05) > 0.05                # longshot shaded up
assert is_resolved(0.995, 0.005) is True
assert is_resolved(0.60, 0.40) is False
print("PASS: calibration + resolution detection")

# --- Test 10: NO-side PnL (regression: was computing wrong sign/scale) ---
from bot.markets import Market  # noqa: E402
tid2 = journal.log_trade_open(
    market_id="test_no", question="NO side test?", side="NO",
    entry_price=0.70, amount_usd=7.0, shares=10.0, edge=0.2,
    reasoning="t", headline="h", news_source="s", classification="bearish",
    materiality=0.8,
)
# Bought NO at 0.70 (YES was 0.30). YES drops to 0.20 → NO now worth 0.80.
# Correct PnL: (0.80 - 0.70) * 10 = +$1.00 (old buggy code gave +$5.00)
pnl_no = journal.log_trade_close(tid2, 0.20, "take_profit")
assert abs(pnl_no - 1.0) < 0.01, f"NO-side PnL wrong: expected 1.0, got {pnl_no}"
print(f"PASS: NO-side PnL correct (got {pnl_no:.2f}, old code gave 5.00)")

# --- Test 11: tick rounding ---
from bot.executor import _round_to_tick  # noqa: E402
assert abs(_round_to_tick(0.567, 0.01) - 0.57) < 1e-9
assert abs(_round_to_tick(0.564, 0.01) - 0.56) < 1e-9
assert abs(_round_to_tick(0.567, 0.1) - 0.6) < 1e-9
assert abs(_round_to_tick(0.1234, 0.001) - 0.123) < 1e-9
print("PASS: tick rounding")

# --- Test 12: token_id fallback for custom outcome names ---
m = Market(
    condition_id="x", question="Winner?", slug="",
    yes_price=0.6, no_price=0.4, volume=1000, end_date="",
    tokens=[
        {"token_id": "tokA", "outcome": "Trump", "price": 0.6},
        {"token_id": "tokB", "outcome": "Harris", "price": 0.4},
    ],
)
assert m.token_id("YES") == "tokA"   # custom names → positional fallback
assert m.token_id("NO") == "tokB"
m2 = Market(
    condition_id="y", question="Q?", slug="",
    yes_price=0.6, no_price=0.4, volume=1000, end_date="",
    tokens=[
        {"token_id": "tokC", "outcome": "Yes", "price": 0.6},
        {"token_id": "tokD", "outcome": "No", "price": 0.4},
    ],
)
assert m2.token_id("YES") == "tokC"  # standard names → label match
assert m2.token_id("NO") == "tokD"
print("PASS: token_id fallback for custom outcome names")

# --- Test 13: min-profit threshold gates clock reset ---
config.SURVIVAL_MIN_PROFIT_USD = 0.50
mon3 = SurvivalMonitor()
mon3.check()
mon3.record_profit(0.30)  # below threshold — must NOT reset
assert abs(mon3.status.total_realized_profit - 0.0) < 1e-9
mon3.record_profit(1.00)  # above threshold — resets
assert abs(mon3.status.total_realized_profit - 1.00) < 1e-9
config.SURVIVAL_MIN_PROFIT_USD = 0.01  # restore
print("PASS: min-profit threshold gates survival clock")

# --- Test 14: py-clob-client installed + API surface ---
from py_clob_client.client import ClobClient  # noqa: E402
from py_clob_client.clob_types import MarketOrderArgs, OrderType  # noqa: E402
assert hasattr(ClobClient, "create_market_order")
assert hasattr(ClobClient, "get_tick_size")
assert OrderType.FAK is not None
print("PASS: py-clob-client installed, market-order API present")

# --- Test 15: quant engine — pure math, no network ---
from bot.quant import _ema, momentum_signal, mean_reversion_signal, flow_signal  # noqa: E402
# EMA sanity: rising series → EMA tracks upward
assert _ema([0.1, 0.2, 0.3, 0.4, 0.5], 3) > _ema([0.5, 0.4, 0.3, 0.2, 0.1], 3)
# Momentum: no history → 0 (neutral, no crash)
assert abs(momentum_signal("fake_token") - 0.0) < 1e-9
assert abs(mean_reversion_signal("fake_token", 0.5) - 0.0) < 1e-9
assert abs(flow_signal("fake_token", 0.5) - 0.0) < 1e-9
print("PASS: quant engine math + graceful no-data handling")

# --- Test 16: quant engine — live free-data signal on a real market ---
from bot.quant import compute_quant_signal  # noqa: E402
from bot.markets import fetch_active_markets, filter_niche  # noqa: E402
ms = None
for attempt in range(3):
    ms = fetch_active_markets(200)
    if ms:
        break
    time.sleep(2)
assert ms, "Gamma API unreachable after 3 retries"
niche = filter_niche(ms)
assert niche, "no niche markets returned"
qs = compute_quant_signal(niche[0])
assert qs.direction in ("bullish", "bearish", "neutral")
assert 0.0 <= qs.strength <= 1.0
print(f"PASS: live quant signal — {niche[0].question[:40]} → {qs.direction} (str={qs.strength}, "
      f"mom={qs.momentum}, mrev={qs.mean_rev}, flow={qs.flow}, srcs={qs.sources_used})")

# --- Test 17: weighted lexicon classifier ---
from bot.classifier import _keyword_classify  # noqa: E402
c1 = _keyword_classify("Fed approves record rate cut as economy surges")
assert c1.direction == "bullish" and c1.materiality >= 0.6
c2 = _keyword_classify("Company files for bankruptcy after fraud investigation")
assert c2.direction == "bearish" and c2.materiality >= 0.6
c3 = _keyword_classify("The meeting is scheduled for Tuesday")
assert c3.direction == "neutral" and abs(c3.materiality - 0.0) < 1e-9
print("PASS: weighted lexicon classifier (bull/bear/neutral + materiality scaling)")

# --- Test 18: TimesFM 2.5 forecaster (skipped when disabled or unavailable) ---
import bot.config as _cfg  # noqa: E402
if _cfg.TIMESFM_ENABLED:
    from bot.timesfm_forecast import forecast_batch, is_available  # noqa: E402
    # Synthetic rising series → forecast must exist and be finite
    hist = [0.10 + 0.001 * i for i in range(60)]  # steady uptrend
    scores = forecast_batch({"selfcheck_token": hist})
    if is_available():
        assert "selfcheck_token" in scores, "batch forecast missing token"
        s = scores["selfcheck_token"]
        assert -1.0 <= s <= 1.0, f"score out of range: {s}"
        print(f"PASS: TimesFM 2.5 forecast — synthetic uptrend score={s:+.3f}")
    else:
        print("SKIP: TimesFM model unavailable (ensemble continues without it)")
else:
    print("SKIP: TimesFM disabled (TIMESFM_ENABLED != true)")

print("\nALL SELF-CHECKS PASSED")
