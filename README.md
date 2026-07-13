# Ani-BL Movie Management Website

Production-ready Flask application built to match `promptweb.md`.

## Stack

- Python Flask
- SQLAlchemy with SQLite
- Flask-Login
- Werkzeug password hashing
- HTML5, CSS3, and vanilla JavaScript

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = "change-this-in-production"
flask --app app run
```

The database is created under `instance/` by default. For Railway or other ephemeral environments, configure the following environment variables:

- `SECRET_KEY`: strong secret
- `DATABASE_URL`: database connection string (for SQLite, point it to a writable path)
- `GOOGLE_DRIVE_ACCOUNT_COUNT`: number of configured Google Drive accounts (default: `1`)
- `GOOGLE_DRIVE_POSTERS_FOLDER_ID`: Google Drive folder ID for poster uploads
- `GOOGLE_DRIVE_VIDEOS_FOLDER_ID`: Google Drive folder ID for video uploads
- `GOOGLE_OAUTH_CLIENT_ID`: OAuth 2.0 client ID for Google Drive API access
- `GOOGLE_OAUTH_CLIENT_SECRET`: OAuth 2.0 client secret for Google Drive API access
- `GOOGLE_OAUTH_REFRESH_TOKEN`: OAuth 2.0 refresh token for Drive uploads
- `GOOGLE_OAUTH_TOKEN_FILE`: optional local refresh token file path

For multiple drive accounts, add indexed variables for account `1+` as needed, for example:

- `GOOGLE_OAUTH_CLIENT_ID_1`
- `GOOGLE_OAUTH_CLIENT_SECRET_1`
- `GOOGLE_OAUTH_REFRESH_TOKEN_1`
- `GOOGLE_OAUTH_TOKEN_FILE_1`
- `GOOGLE_DRIVE_POSTERS_FOLDER_ID_1`
- `GOOGLE_DRIVE_VIDEOS_FOLDER_ID_1`

Update `GOOGLE_DRIVE_ACCOUNT_COUNT` to match the number of accounts.

## Railway Deployment Notes

- The app uses Google Drive for persistent poster and video storage.
- Railway receives only temporary upload data; files are immediately uploaded to Drive and removed from disk.
- If OAuth environment variables are provided, the app uses OAuth 2.0 refresh-token auth.
- If OAuth values are missing and a local service account path or `GOOGLE_SERVICE_ACCOUNT_JSON` exists, the app falls back to service account auth.
- No Google Drive folder IDs are hardcoded in source.

## Implementation Decisions

- Management pages and MP4 playback require authentication.
- Posters and movie covers are public so the home page can render featured content.
- Users can edit and delete only their own posters and movies.
- Uploads are validated by extension, browser MIME type, and file signature.
- Images are limited to 8 MB because the spec only defines the 5 GB video limit.
- Author information is configurable with `AUTHOR_NAME`, `AUTHOR_ROLE`, and `AUTHOR_BIO`.
