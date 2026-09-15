import sqlite3, os
if os.path.exists('data/trades.db'):
    conn = sqlite3.connect('data/trades.db')
    open_t = conn.execute("SELECT COUNT(*) FROM trades WHERE status='open'").fetchone()[0]
    total_t = conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
    pnl = conn.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM trades WHERE status!='open'").fetchone()[0]
    print('DB:', total_t, 'trades,', open_t, 'open, PnL=', pnl)
else:
    print('DB MISSING')
if os.path.exists('data/logs/bot.log'):
    lines = open('data/logs/bot.log', encoding='utf-8', errors='ignore').readlines()
    print('Log:', len(lines), 'lines')
    for l in lines[-3:]:
        print('  ', l.strip()[:100])
else:
    print('Log MISSING')
print('SECURITY_NOTE:', 'present' if os.path.exists('SECURITY_NOTE.md') else 'missing')
