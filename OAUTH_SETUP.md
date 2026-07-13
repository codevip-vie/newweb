# OAuth 2.0 Setup for Ani-BL Google Drive Storage

## Modified Files

- `google_drive.py`
  - Replaced service account upload/delete credential handling with OAuth 2.0 Authorization Code Flow.
  - Added refresh token persistence via `GOOGLE_OAUTH_REFRESH_TOKEN` or local `GOOGLE_OAUTH_TOKEN_FILE`.
  - Added authorization URL generation and authorization code exchange helpers.
  - Kept existing helper names unchanged: `upload_file()`, `upload_poster()`, `upload_video()`, `delete_file()`, `replace_file()`, `exists()`, `get_file_url()`.

- `config.py`
  - Added `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`, and `GOOGLE_OAUTH_TOKEN_FILE` config values.

- `routes/main.py`
  - Added admin-only OAuth routes:
    - `/dashboard/google-oauth/authorize`
    - `/dashboard/google-oauth/callback`
  - These routes do not change existing user or admin workflows.

- `.env.example`
  - Added OAuth environment variables example, including optional token file path.

- `README.md`
  - Updated Drive auth documentation to explain OAuth usage.

## Why These Files Were Modified

- `google_drive.py` is the central storage module; it now obtains Drive credentials through OAuth instead of relying on service account JSON.
- `config.py` is where environment variables are declared for the app.
- `routes/main.py` needed new callback endpoints to complete the authorization code flow for the owner/admin.
- `.env.example` provides correct environment setup guidance for local and Railway deployment.
- `README.md` documents the new OAuth method and the required environment settings.

## Google Cloud APIs to Enable

- Google Drive API

## OAuth Client Configuration

1. Open Google Cloud Console.
2. Go to APIs & Services > Credentials.
3. Create an OAuth 2.0 Client ID for a Web application.
4. Add the redirect URI below.
5. Copy the generated Client ID and Client Secret into the app environment.

## Exact Redirect URI

- `/dashboard/google-oauth/callback`
- Full redirect URI:
  - `https://<your-domain>/dashboard/google-oauth/callback`

Use this exact URI in Google Cloud OAuth Client settings.

## Required Railway Variables

- `SECRET_KEY`
- `DATABASE_URL`
- `GOOGLE_DRIVE_POSTERS_FOLDER_ID`
- `GOOGLE_DRIVE_VIDEOS_FOLDER_ID`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REFRESH_TOKEN` (preferred for Railway)
- `GOOGLE_OAUTH_TOKEN_FILE` (optional, local path fallback)

## How to Authorize Using `codeupperank@gmail.com`

1. Deploy or run the app locally with `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` defined.
2. Log in as an administrator.
3. Visit `/dashboard/google-oauth/authorize`.
4. Sign in with `codeupperank@gmail.com` on the Google consent screen.
5. Grant Drive access when prompted.
6. The callback route will save the returned refresh token automatically.

For Railway, if the token file cannot persist, copy the refresh token into `GOOGLE_OAUTH_REFRESH_TOKEN`.

## How Refresh Tokens Are Stored

- If `GOOGLE_OAUTH_REFRESH_TOKEN` is set, the app uses that value directly.
- Otherwise the app saves the refresh token into `GOOGLE_OAUTH_TOKEN_FILE`.
- Default token file path: `instance/google_drive_oauth.json`.

## How to Deploy

1. Set the required environment variables in Railway.
2. Ensure `GOOGLE_DRIVE_POSTERS_FOLDER_ID` and `GOOGLE_DRIVE_VIDEOS_FOLDER_ID` are set.
3. Ensure `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` are set.
4. If possible, also provide `GOOGLE_OAUTH_REFRESH_TOKEN`.
5. Deploy the app normally; no source code changes are required between local and Railway.

## How to Test Upload

1. Log in as a normal user or administrator.
2. Create a new poster or movie.
3. Verify that the upload succeeds and the file appears in Drive.
4. Confirm the returned media URL uses `drive.google.com/uc?export=download&id=...`.

## How to Test Delete

1. Delete a poster or movie from the app.
2. Confirm the database record is removed.
3. Verify the associated file is deleted from Google Drive.

## How to Test Replace

1. Edit a poster/movie and upload a new file.
2. Confirm the new file is uploaded successfully.
3. Confirm the old Drive file is deleted.
4. Confirm the database references the new Drive file ID.
