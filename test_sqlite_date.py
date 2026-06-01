import sqlite3
conn = sqlite3.connect(':memory:')
c = conn.cursor()
c.execute("SELECT CAST('2026-06-01' AS DATE)")
print('cast:', repr(c.fetchone()[0]))
