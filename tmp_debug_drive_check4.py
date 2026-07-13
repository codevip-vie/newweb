import json
import hashlib
import sqlite3
import os
from pathlib import Path
import config
import google_drive

print('cwd', Path.cwd())
print('loaded env GOOGLE_DRIVE_SYSTEM_FOLDER_ID=', os.environ.get('GOOGLE_DRIVE_SYSTEM_FOLDER_ID'))
print('loaded env GOOGLE_OAUTH_REFRESH_TOKEN present=', bool(os.environ.get('GOOGLE_OAUTH_REFRESH_TOKEN')))
print('GOOGLE_SERVICE_ACCOUNT_JSON present=', bool(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')))
print('TOKEN_FILE', os.environ.get('GOOGLE_OAUTH_TOKEN_FILE'))
print('TOKEN_FILE exists', Path(os.environ.get('GOOGLE_OAUTH_TOKEN_FILE') or 'instance/google_drive_oauth.json').exists())

local_meta_path = Path('metadata/latest.json')
assert local_meta_path.exists(), 'local latest metadata missing'
local_meta = json.loads(local_meta_path.read_text(encoding='utf-8'))
print('local latest metadata:', local_meta)

creds = google_drive._load_credentials(None)
print('creds type', type(creds), 'valid', getattr(creds, 'valid', None), 'expired', getattr(creds, 'expired', None))
service = google_drive._build_service(creds)
print('service built')

system_folder_id = os.environ.get('GOOGLE_DRIVE_SYSTEM_FOLDER_ID')
assert system_folder_id, 'system folder id env missing'

metadata_folder_id = google_drive.search_file_id_by_name(None, 'metadata', folder_id=system_folder_id, mime_type_prefix='application/vnd.google-apps.folder')
print('metadata_folder_id', metadata_folder_id)
assert metadata_folder_id, 'metadata folder id not found'

latest_json_id = google_drive.search_file_id_by_name(None, 'latest.json', folder_id=metadata_folder_id, mime_type_prefix='application/json')
print('remote latest.json id', latest_json_id)
remote_latest_content = google_drive.download_text(None, latest_json_id)
remote_latest = json.loads(remote_latest_content)
print('remote latest metadata:', remote_latest)

if local_meta.get('backup_file_id') == remote_latest.get('backup_file_id'):
    print('local latest and remote latest reference same backup file id')
else:
    print('local latest and remote latest differ')

# check both backup files
for label, file_id in [('local_latest', local_meta.get('backup_file_id')), ('remote_latest', remote_latest.get('backup_file_id'))]:
    if not file_id:
        print(label, 'missing file_id')
        continue
    print('---', label, file_id)
    try:
        file_meta = service.files().get(fileId=file_id, fields='id,name,mimeType,size,createdTime,modifiedTime').execute()
        print('file_meta', file_meta)
    except Exception as e:
        print('file_meta_error', repr(e))
        continue
    out_path = Path(f'instance/tmp_restore_probe_{label}.sqlite3')
    if out_path.exists():
        out_path.unlink()
    try:
        downloaded = google_drive.download_file(None, file_id, out_path)
        print('downloaded', downloaded, 'size', downloaded.stat().st_size)
        with downloaded.open('rb') as f:
            head = f.read(64)
        print('head bytes', head[:64])
        print('head ascii', ''.join(chr(b) if 32 <= b < 127 else '.' for b in head))
        print('sha256', hashlib.sha256(downloaded.read_bytes()).hexdigest())
        conn = sqlite3.connect(downloaded)
        cur = conn.cursor()
        cur.execute('PRAGMA integrity_check;')
        print('integrity_check', cur.fetchone())
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cur.fetchall()]
        print('tables', tables)
        try:
            cur.execute("SELECT metadata_value FROM backup_metadata WHERE metadata_key='generation';")
            print('generation row', cur.fetchone())
        except Exception as e:
            print('backup_metadata error', repr(e))
        conn.close()
    except Exception as e:
        print('download/inspect error', repr(e))

# list database folder contents
database_folder_id = google_drive.search_file_id_by_name(None, 'database', folder_id=system_folder_id, mime_type_prefix='application/vnd.google-apps.folder')
print('database_folder_id', database_folder_id)
if database_folder_id:
    files = service.files().list(q=f"'{database_folder_id}' in parents and trashed = false", fields='files(id,name,mimeType,size)').execute().get('files', [])
    print('database folder files count', len(files))
    for file in files:
        print(file)

print('done')
