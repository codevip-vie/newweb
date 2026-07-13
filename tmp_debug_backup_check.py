import json
import hashlib
import sqlite3
from pathlib import Path
import google_drive

metadata_path = Path('metadata/latest.json')
print('metadata_exists', metadata_path.exists())
latest = json.loads(metadata_path.read_text(encoding='utf-8'))
print('backup_file_id', latest.get('backup_file_id'))
print('backup_filename', latest.get('backup_filename'))
print('database_size', latest.get('database_size'))
print('sha256', latest.get('sha256'))

file_id = latest.get('backup_file_id')
print('loading credentials')
try:
    creds = google_drive._load_credentials(None)
    print('creds loaded', type(creds), getattr(creds, 'valid', None), getattr(creds, 'expired', None))
except Exception as e:
    print('load_credentials_error', repr(e))
    creds = None

service = None
if creds is not None:
    try:
        service = google_drive._build_service(creds)
        print('service ok', service is not None)
    except Exception as e:
        print('build_service_error', repr(e))

if service is not None:
    try:
        meta = service.files().get(fileId=file_id, fields='id,name,mimeType,size,createdTime,modifiedTime').execute()
        print('drive_meta', meta)
    except Exception as e:
        print('drive_meta_error', repr(e))

from google_drive import download_file
out_path = Path('instance/tmp_restore_probe.sqlite3')
if out_path.exists():
    out_path.unlink()
try:
    path = download_file(None, file_id, out_path)
    print('downloaded path', path)
    print('downloaded size', path.stat().st_size)
    with path.open('rb') as f:
        head = f.read(64)
    print('head_bytes', head[:64])
    print('head_ascii', ''.join(chr(b) if 32 <= b < 127 else '.' for b in head))
    print('sha256', hashlib.sha256(path.read_bytes()).hexdigest())
except Exception as e:
    print('download_error', repr(e))

if out_path.exists():
    conn = sqlite3.connect(out_path)
    cur = conn.cursor()
    try:
        cur.execute('PRAGMA integrity_check;')
        print('integrity', cur.fetchone())
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cur.fetchall()]
        print('tables', tables)
        cur.execute("SELECT metadata_value FROM backup_metadata WHERE metadata_key='generation';")
        print('generation row', cur.fetchone())
    except Exception as e:
        print('sqlite inspection error', repr(e))
    finally:
        conn.close()
