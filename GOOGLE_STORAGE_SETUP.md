# LifeOS — GitHub Pages + Google Apps Script setup

The repository now includes a static GitHub Pages frontend at the root `index.html`. GitHub Pages cannot run Flask/Python, so this frontend communicates with the dedicated LifeOS Apps Script API through a hidden iframe and `postMessage`.

## 1. Publish the static frontend

1. In the GitHub repository, open **Settings → Pages**.
2. Set **Deploy from a branch**, branch `main`, folder `/(root)` (or use the publishing source already configured for this repository).
3. Save and wait for GitHub Pages to publish the root `index.html`.
4. Open the published page while signed in to the same Google account that owns the Apps Script deployment.

The root page uses `static/style.css`, `static/favicon.svg`, and `static/pages-app.js`. The Flask templates are kept for reference but are not used by GitHub Pages.

## 2. Configure the Google Apps Script deployment

The static frontend must not contain a shared API secret. The API uses the Google Apps Script deployment access control instead.

1. Open the existing LifeOS Apps Script project and replace its code with the current repository file: `google-apps-script/LifeOSApi.gs`.
2. Run `setupLifeOSDatabase()` once from the editor and approve Google Sheets access. This creates/opens the spreadsheet and initializes Tasks, Notes, and Sites.
3. Choose **Deploy → Manage deployments → Edit** (pencil) or create a new web app deployment.
4. Set **Execute as: Me**.
5. Set **Who has access: Only myself**. This matters: the static frontend does not send an API token, so the deployment must be restricted to the owner Google account.
6. Select **New version** and deploy. Copy the URL ending in `/exec`.
7. In `index.html`, check the form action URL and in `static/pages-app.js`, check `API_URL`. Both must match the current deployment URL. The currently configured URL is the one the user supplied in this project.

Do not set access to “Anyone”. The iframe transport is intended to be protected by Google sign-in and the “Only myself” deployment setting. Never put `API_TOKEN` in browser JavaScript or commit a secret to GitHub.

## 3. Test it

1. Open the GitHub Pages URL in a browser where you are signed in to the Google account that owns the Apps Script deployment.
2. Wait for the status message to say that Google Sheets is connected.
3. Add a test task, click the page refresh button, and verify the task remains.
4. Save today's note and register a test site URL, then reload and verify both remain.
5. Try **Export backup** and confirm a JSON file downloads. Only test restore with a backup you trust.

If the page times out or reports a connection error, open the Apps Script editor and check **Executions**, confirm the latest code was deployed as a new version, and ensure access is set to **Only myself**. Google may show a sign-in/authorization screen the first time.

## Data and security notes

- Tasks, daily notes, and site/repository URLs are stored in the LifeOS Google Spreadsheet.
- The browser transport uses a hidden iframe because a normal cross-origin `fetch()` to Apps Script is not reliable for this response pattern.
- The browser never needs the shared `API_TOKEN`. The iframe request uses a deployment that should only be accessible to the owner account.
- The old Flask `app.py` remains in the repository, but GitHub Pages does not execute it. Do not configure Render environment variables for the Pages frontend.
- Existing SQLite data is not automatically imported into the spreadsheet. If you have a JSON backup from the old version, use the restore control after the connection works.
- Habit tracking is not currently included in the GitHub Pages frontend/API.
