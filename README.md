# OFAC Batch Checker

Internal web app for running batch name checks against the official OFAC Sanctions List Search website and saving each result page as a PDF.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\playwright install chromium
cd frontend
npm install
```

## Authentication

The app fails closed until authentication environment variables are set.
Do not commit real passwords, password hashes, or session secrets.

Generate the password hash:

```powershell
.\venv\Scripts\python scripts\hash_password.py
```

Generate a session secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Create a private `.env` or server environment with:

```text
OFAC_SESSION_SECRET=replace-with-a-long-random-secret
OFAC_PASSWORD_HASH=hash-from-script
OFAC_COOKIE_SECURE=false
OFAC_SESSION_TTL_SECONDS=43200
```

Set `OFAC_COOKIE_SECURE=true` when serving the site over HTTPS.

For a Linux `systemd` deployment, put the real values in a private file:

```bash
sudo nano /etc/ofac-checker.env
```

```text
OFAC_SESSION_SECRET=replace-with-a-long-random-secret
OFAC_PASSWORD_HASH=hash-from-script
OFAC_COOKIE_SECURE=true
OFAC_SESSION_TTL_SECONDS=43200
```

Then add this line under `[Service]` in `ofac-checker.service`:

```ini
EnvironmentFile=/etc/ofac-checker.env
```

## Run

Backend:

```powershell
$env:OFAC_SESSION_SECRET = "replace-with-a-long-random-secret"
$env:OFAC_PASSWORD_HASH = "hash-from-script"
.\venv\Scripts\uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm run dev
```

Open http://127.0.0.1:5173.

## Storage

Each run is stored as local files under `storage/runs/{run_id}/`:

- `run.json` contains the run status and result metadata.
- Generated PDFs are stored beside the manifest.

The browser remembers only the most recent run ID so refreshing the page can reopen the latest batch.
