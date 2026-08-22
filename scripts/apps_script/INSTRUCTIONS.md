# Deploying the GuOnco Sheets backend (~5 minutes, one time)

1. Go to <https://sheets.new> and create a blank spreadsheet named
   **GuOnco Registry**.
2. In the spreadsheet: **Extensions → Apps Script**.
3. Delete whatever is in `Code.gs` and paste the full contents of
   `scripts/apps_script/Code.gs` (generated next to this file).
4. Click **Deploy → New deployment → Web app** and set:
   - Description: `GuOnco v1`
   - Execute as: **Me**
   - Who has access: **Anyone**  ← required so your local app can POST
5. Click **Deploy**, authorize when prompted, and copy the **Web app URL**
   (ends in `/exec`).
6. Put that URL in your `.env`:
   ```
   APPS_SCRIPT_URL=https://script.google.com/macros/s/XXXX/exec
   ```
7. Restart the GuOnco server and press **Sincronizar** in the app.
   One tab per pathology appears in the spreadsheet automatically.

## Notes

- Re-syncing never duplicates: rows are upserted by `_id`.
- Sheets store human-readable bilingual cells (`CODE (es/en)`), while your
  SQLite database keeps pure codes — the spreadsheet is a readable mirror,
  not the source of truth.
- To re-deploy after regenerating `Code.gs`: Deploy → Manage deployments →
  Edit → New version → Deploy (the `/exec` URL stays the same).
