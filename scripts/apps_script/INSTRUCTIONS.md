# Deploying the GuOnco Sheets backend (~5 minutes)

## First deployment

1. Go to <https://sheets.new> and create a blank spreadsheet named
   **GuOnco Registry**.
2. In the spreadsheet: **Extensions → Apps Script**.
3. Delete whatever is in `Code.gs` and paste the full contents of
   `scripts/apps_script/Code.gs` (generated next to this file).
4. **Set your secret**: near the top of `Code.gs`, replace
   `CAMBIA-ESTE-SECRETO / CHANGE-THIS-SECRET` with a long random string,
   then put the SAME value in your `.env`:
   ```
   SCRIPT_SECRET=the-same-long-random-string
   ```
5. Click **Deploy → New deployment → Web app** and set:
   - Description: `GuOnco v2`
   - Execute as: **Me**
   - Who has access: **Anyone**  ← required so your app can POST
6. Click **Deploy**, authorize when prompted, and copy the **Web app URL**
   (ends in `/exec`).
7. Put that URL in your `.env`:
   ```
   APPS_SCRIPT_URL=https://script.google.com/macros/s/XXXX/exec
   ```

## Re-deploying (upgrading from v1)

1. Paste the new `Code.gs` over the old one and **set the secret** (step 4 above).
2. Deploy → **Manage deployments** → Edit → **New version** → Deploy
   (the `/exec` URL stays the same).
3. Existing rows keep working: the script automatically appends the new
   `_creado_por`, `_actualizado_por` and `_json` columns to old sheets.
4. Press **Sincronizar** in the app once so existing records gain their
   `_json` column (needed for reads in `STORE=sheets` mode).

## Notes

- Re-syncing never duplicates: rows are upserted by `_id`.
- Display columns stay human-readable (`CODE (es/en)`); the `_json`
  column stores the raw-code record that the app reads back.
- `registrado_por` attribution shows who captured each case.
- Requests without the shared secret are rejected — keep it private.
