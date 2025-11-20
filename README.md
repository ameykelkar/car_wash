# Car Wash Tracker

Streamlit-powered dashboard for logging every wash from a $79.99/month membership and comparing the cost against the $40 à-la-carte price.

## Features
- One-click button to record today's wash; automatically prevents duplicate logs for the same day.
- Membership summary showing next renewal date (25th) and total savings to date.
- Billing-cycle filter (25th → 24th) to inspect washes and savings for any recorded cycle, plus an all-time aggregate tied to the membership start date.
- Persistent storage via Google Sheets so history survives redeploys.
- Recent history table pulled from the sheet with friendly formatting.
- Optional PIN gate (set `log_pin` in Streamlit secrets) before logging a new wash.

## Requirements
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Python 3.10+

## Setup
1. Install dependencies into a virtual environment managed by uv:
   ```bash
   uv sync
   ```
2. Run the Streamlit app with uv:
   ```bash
   uv run streamlit run streamlit_app.py
   ```

## Deploying to Streamlit Community Cloud
1. Push the repo (including `requirements.txt` and `streamlit_app.py`) to GitHub.
2. Visit https://share.streamlit.io/, click **New app**, and select this repository and branch.
3. Set the entry point to `streamlit_app.py`.
4. In **App Settings → Secrets**, paste the same contents you use locally for `gcp_service_account`, `google_sheet_id`, and (optionally) `google_worksheet_name`.
5. The platform installs dependencies from `requirements.txt`; subsequent pushes to the same branch redeploy automatically.

## Google Sheets backend
The app reads and writes directly to Google Sheets so data survives Streamlit redeploys.

1. Create a Google Cloud project, enable the **Google Sheets API**, and generate a service account JSON key.
2. Share the target spreadsheet with the service account email so it can edit the sheet.
3. Add credentials to `.streamlit/secrets.toml` (or Streamlit Cloud secrets) using:
   ```toml
   google_sheet_id = "YOUR_SHEET_ID"  # the long ID from the sheet URL
   google_worksheet_name = "car_washes"  # optional; defaults to this value

   [gcp_service_account]
   type = "service_account"
   project_id = "..."
   private_key_id = "..."
   private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
   client_email = "service-account@project.iam.gserviceaccount.com"
   client_id = "..."
   ```
4. Alternatively, set the environment variables `GOOGLE_SERVICE_ACCOUNT_JSON` (raw JSON string) and `GOOGLE_SHEET_ID`.

The first time the app runs it will create (or reuse) a worksheet named `car_washes` with columns `id`, `date`, and `price`. You can manually seed the spreadsheet with existing wash history via Google Sheets UI if desired.

## Configuration
- Membership start date (used to determine how many $79.99 billing cycles have been charged) is defined in `streamlit_app.py` via the `MEMBERSHIP_START_DATE` constant. Update it if the subscription begins on a different day.
