# LifeOS Google Sheets storage setup

LifeOS can keep tasks, daily notes, and saved site/repository URLs in a dedicated Google Spreadsheet through Google Apps Script. The Apps Script API is in `google-apps-script/LifeOSApi.gs`.

## 1. Create the private database API

1. Open https://script.google.com/ and create a **new standalone project**. Do not use the EA-deta Apps Script project.
2. Replace the editor's contents with the complete contents of `google-apps-script/LifeOSApi.gs` from this repository.
3. Open **Project Settings → Script Properties** and add:
   - `API_TOKEN`: a long, random secret value. Use a different value from any other project.
4. Select `setupLifeOSDatabase` in the function dropdown and click **Run**. Review and approve the requested Google Sheets permissions. This creates a spreadsheet named **LifeOS Database** and saves its ID in Script Properties.
5. Choose **Deploy → New deployment → Web app**.
   - Execute as: **Me**
   - Who has access: **Anyone** (the API validates the secret token itself; the token must remain private)
6. Deploy, authorize if prompted, and copy the URL ending in `/exec`. Do not use a `/dev` test URL.

Keep the script and spreadsheet private. Anyone who has both the web-app URL and the secret token could read or change the LifeOS data. Never put the token in browser JavaScript or commit it to GitHub.

## 2. Configure Render

In the Render dashboard for the LifeOS web service, open **Environment** and add:

- `LIFEOS_GAS_API_URL`: the deployed Apps Script URL ending in `/exec`
- `LIFEOS_GAS_API_TOKEN`: the exact same secret value as the Apps Script `API_TOKEN`

Save changes and wait for Render to redeploy. The Flask server sends requests to Apps Script, so the secret is not sent to the browser.

## 3. Preserve existing LifeOS data

**Export a backup before switching storage.**

1. Before adding the two Render variables, open LifeOS and choose **Data management → Export backup**.
2. Configure the Apps Script API and Render variables as above.
3. Once the new deployment is running, sign in to LifeOS and use **Restore from backup** to import the JSON file. This writes the backup's tasks, notes, and sites into the new LifeOS spreadsheet.
4. Add a small test task, refresh the page, and confirm it remains. Then delete the test task if desired.

Do not delete the old backup until the import and persistence test succeed. The old SQLite database is not migrated automatically.

## Supported storage actions

- Task add, toggle, delete
- Save today's note (older dated notes remain available)
- Add/delete saved sites, including GitHub repository URLs
- JSON export/import for tasks, notes, and sites

Habit tracking is not currently wired to the Google API. If you later re-enable habits in the UI, its storage path must be added separately.

## Troubleshooting

- If the page reports it cannot connect to Google storage, check both Render variables, the Apps Script deployment URL, and Apps Script **Executions**.
- If the API returns Unauthorized, make sure the two `API_TOKEN` values match exactly.
- After changing Apps Script code, create a new version and update the web-app deployment to that version.
- Without both Render variables, LifeOS continues to use its existing SQLite mode. SQLite data on a service without a persistent disk can be lost when the instance is replaced; the Google API is not active until configuration is complete.
