import json
import hashlib
import os
import sqlite3
from pathlib import Path

import config
import google_drive

print('WORKDIR', Path.cwd())
print('ENV GOOGLE_DRIVE_SYSTEM_FOLDER_ID=', os.environ.get('GOOGLE_DRIVE_SYSTEM_FOLDER_ID'))
print('ENV GOOGLE_SERVICE_ACCOUNT=', repr(os.environ.get('GOOGLE_SERVICE_ACCOUNT')))
print('ENV GOOGLE_SERVICE_ACCOUNT_JSON=', bool(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')))
print('ENV GOOGLE_OAUTH_REFRESH_TOKEN=', bool(os.environ.get('GOOGLE_OAUTH_REFRESH_TOKEN')))
print('TOKEN_FILE', os.environ.get('GOOGLE_OAUTH_TOKEN_FILE'))
print('TOKEN_FILE exists', Path(os.environ.get('GOOGLE_OAUTH_TOKEN_FILE') or 'instance/google_drive_oauth.json').exists())
print('LOCAL latest.json exists', Path('metadata/latest.json').exists())

metadata_path = Path('metadata/latest.json')
if metadata_path.exists():
    latest = json.loads(metadata_path.read_text(encoding='utf-8'))
    print('LOCAL latest backup_file_id', latest.get('backup_file_id'))
    print('LOCAL latest backup_filename', latest.get('backup_filename'))
    print('LOCAL latest database_size', latest.get('database_size'))
    print('LOCAL latest sha256', latest.get('sha256'))
else:
    latest = None

try:
    creds = google_drive._load_credentials(None)
    print('CREDS TYPE', type(creds), 'valid', getattr(creds, 'valid', None), 'expired', getattr(creds, 'expired', None))
except Exception as exc:
    print('CRED_LOAD_ERROR', repr(exc))
    creds = None

service = None
if creds is not None:
    try:
        service = google_drive._build_service(creds)
        print('SERVICE built')
    except Exception as exc:
        print('BUILD_SERVICE_ERROR', repr(exc))

if service is not None and os.environ.get('GOOGLE_DRIVE_SYSTEM_FOLDER_ID'):
    system_folder_id = os.environ['GOOGLE_DRIVE_SYSTEM_FOLDER_ID']
    print('SYSTEM FOLDER ID', system_folder_id)
    try:
        metadata_folder_id = google_drive.search_file_id_by_name(None, 'metadata', folder_id=system_folder_id, mime_type_prefix='application/vnd.google-apps.folder')
        print('metadata_folder_id via search', metadata_folder_id)
    except Exception as exc:
        print('search metadata folder error', repr(exc))
        metadata_folder_id = None

    if metadata_folder_id:
        try:
            print('listing metadata folder contents')
            files = service.files().list(q=f"'{metadata_folder_id}' in parents and trashed = false", fields='files(id,name,mimeType,size)').execute().get('files', [])
            print('metadata folder items', len(files))
            for item in files:
                print('METADATA ITEM', item)
        except Exception as exc:
            print('list metadata folder error', repr(exc))

        try:
            latest_file_id = google_drive.search_file_id_by_name(None, 'latest.json', folder_id=metadata_folder_id, mime_type_prefix='application/json')
            print('remote latest.json file_id', latest_file_id)
            if latest_file_id:
                remote_latest = google_drive.download_text(None, latest_file_id)
                print('remote latest.json content', remote_latest)
        except Exception as exc:
            print('remote latest.json error', repr(exc))
    else:
        print('metadata folder not found')

    if service is not None and latest is not None:
        file_id = latest.get('backup_file_id')
        if file_id:
            try:
                file_meta = service.files().get(fileId=file_id, fields='id,name,mimeType,size,createdTime,modifiedTime').execute()
                print('remote backup file meta', file_meta)
            except Exception as exc:
                print('remote backup meta error', repr(exc))

            try:
                download_path = Path('instance/tmp_restore_probe.sqlite3')
                if download_path.exists():
                    download_path.unlink()
                downloaded = google_drive.download_file(None, file_id, download_path)
                print('downloaded file', downloaded, 'size', downloaded.stat().st_size)
                with downloaded.open('rb') as f:
                    head = f.read(64)
                print('head', head[:64])
                print('head_ascii', ''.join(chr(b) if 32 <= b < 127 else '.' for b in head))
                print('downloaded sha256', hashlib.sha256(downloaded.read_bytes()).hexdigest())
                conn = sqlite3.connect(downloaded)
                cur = conn.cursor()
                cur.execute('PRAGMA integrity_check;')
                print('integrity_check', cur.fetchone())
                cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                print('tables', [row[0] for row in cur.fetchall()])
                try:
                    cur.execute("SELECT metadata_value FROM backup_metadata WHERE metadata_key='generation';")
                    print('generation row', cur.fetchone())
                except Exception as exc:
                    print('backup_metadata error', repr(exc))
                conn.close()
            except Exception as exc:
                print('download/inspect error', repr(exc))

print('DONE')
