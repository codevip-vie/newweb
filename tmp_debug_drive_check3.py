import json
import hashlib
import os
from pathlib import Path
import sqlite3
import google_drive

print('cwd', Path.cwd())
print('env system_folder_id', os.environ.get('GOOGLE_DRIVE_SYSTEM_FOLDER_ID'))
print('env oauth_refresh_token', bool(os.environ.get('GOOGLE_OAUTH_REFRESH_TOKEN')))
print('env service account', os.environ.get('GOOGLE_SERVICE_ACCOUNT'))

metadata = json.loads(Path('metadata/latest.json').read_text(encoding='utf-8'))
print('local latest metadata generation', metadata.get('database_generation'))
print('local latest backup_file_id', metadata.get('backup_file_id'))
print('local latest backup_filename', metadata.get('backup_filename'))
print('local latest sha256', metadata.get('sha256'))

creds = google_drive._load_credentials(None)
print('creds', type(creds), getattr(creds, 'valid', None), getattr(creds, 'expired', None))
service = google_drive._build_service(creds)

sys_folder = os.environ.get('GOOGLE_DRIVE_SYSTEM_FOLDER_ID')
if not sys_folder:
    raise SystemExit('no system folder id')

# find folders
metadata_folder_id = google_drive.search_file_id_by_name(None, 'metadata', folder_id=sys_folder, mime_type_prefix='application/vnd.google-apps.folder')
database_folder_id = google_drive.search_file_id_by_name(None, 'database', folder_id=sys_folder, mime_type_prefix='application/vnd.google-apps.folder')
print('metadata_folder_id', metadata_folder_id)
print('database_folder_id', database_folder_id)

# list metadata folder
if metadata_folder_id:
    files = service.files().list(q=f"'{metadata_folder_id}' in parents and trashed = false", fields='files(id,name,mimeType,size)').execute().get('files', [])
    print('metadata folder files:')
    for item in files:
        print(item)
    latest_file_id = google_drive.search_file_id_by_name(None, 'latest.json', folder_id=metadata_folder_id, mime_type_prefix='application/json')
    print('resolved latest.json file_id', latest_file_id)
    if latest_file_id:
        content = google_drive.download_text(None, latest_file_id)
        print('remote latest.json content:')
        print(content)

# list database folder
if database_folder_id:
    files = service.files().list(q=f"'{database_folder_id}' in parents and trashed = false", fields='files(id,name,mimeType,size)').execute().get('files', [])
    print('database folder files:')
    for item in files:
        print(item)

# download both local backup_file_id and remote latest backup_id
ids_to_check = [metadata.get('backup_file_id')]
if latest_file_id:
    remote_latest = json.loads(content)
    ids_to_check.append(remote_latest.get('backup_file_id'))

for idx, file_id in enumerate(filter(None, ids_to_check), start=1):
    print('--- checking file_id', file_id)
    try:
        file_meta = service.files().get(fileId=file_id, fields='id,name,mimeType,size,createdTime,modifiedTime').execute()
        print('file_meta', file_meta)
    except Exception as exc:
        print('file_meta_error', repr(exc))
        continue
    out_path = Path(f'instance/tmp_restore_probe_{idx}.sqlite3')
    if out_path.exists():
        out_path.unlink()
    try:
        download_file = google_drive.download_file(None, file_id, out_path)
        print('downloaded', download_file, 'size', out_path.stat().st_size)
        with out_path.open('rb') as f:
            head = f.read(64)
        print('head_ascii', ''.join(chr(b) if 32 <= b < 127 else '.' for b in head))
        print('sha256', hashlib.sha256(out_path.read_bytes()).hexdigest())
        conn = sqlite3.connect(out_path)
        cur = conn.cursor()
        cur.execute('PRAGMA integrity_check;')
        print('integrity_check', cur.fetchone())
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cur.fetchall()]
        print('tables', tables)
        try:
            cur.execute("SELECT metadata_value FROM backup_metadata WHERE metadata_key='generation';")
            print('gen', cur.fetchone())
        except Exception as exc:
            print('backup_metadata error', repr(exc))
        conn.close()
    except Exception as exc:
        print('download/inspect error', repr(exc))
print('done')
