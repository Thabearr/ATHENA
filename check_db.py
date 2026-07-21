import sqlite3
c = sqlite3.connect('database/athena.db')
print('TABLES:', [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
print()
print('TEAMS columns:')
for r in c.execute('PRAGMA table_info(teams)').fetchall():
    print(' ', r)
print()
print('HISTORICAL_MATCHES columns:')
for r in c.execute('PRAGMA table_info(historical_matches)').fetchall():
    print(' ', r)
print()
print('Team count:', c.execute('SELECT COUNT(*) FROM teams').fetchone()[0])
print('Match count:', c.execute('SELECT COUNT(*) FROM historical_matches').fetchone()[0])
print()
print('Sample teams:')
for r in c.execute('SELECT * FROM teams LIMIT 5').fetchall():
    print(' ', r)
c.close()
