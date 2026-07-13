import sqlite3
from pathlib import Path
import re

DB_PATH = Path('instance/movie_manager.sqlite3')
print('DB exists:', DB_PATH.exists())
if not DB_PATH.exists():
    raise SystemExit(1)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
rows = []
for table, filename in [('movies', 'cover_filename'), ('posters', 'image_filename')]:
    cur.execute(f'SELECT id, title, {filename} FROM {table}')
    rows = cur.fetchall()
    invalid = []
    for row in rows:
        value = row[2]
        if not value:
            invalid.append((row[0], value, 'empty'))
            continue
        if value.startswith('http://') or value.startswith('https://'):
            invalid.append((row[0], value, 'url'))
            continue
        if '/' in value:
            invalid.append((row[0], value, 'contains slash'))
            continue
        if len(value) < 20 or not re.fullmatch(r'[A-Za-z0-9_.-]+', value):
            invalid.append((row[0], value, 'invalid id'))
    print(f'{table}: total={len(rows)} invalid={len(invalid)}')
    if invalid:
        print('examples:', invalid[:10])
conn.close()
