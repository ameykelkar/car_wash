# Car Wash Tracker

Streamlit-powered dashboard for logging every wash from a $79.99/month membership and comparing the cost against the $40 à-la-carte price.

## Features
- One-click button to record today's wash; automatically prevents duplicate logs for the same day.
- Membership summary showing next renewal date (25th) and total savings to date.
- Billing-cycle filter (25th → 24th) to inspect washes and savings for any recorded cycle, plus an all-time aggregate tied to the membership start date.
- Recent history table backed by a lightweight CSV database committed to the repo.

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
3. Set the entry point to `streamlit_app.py`. No extra secrets are required because storage is committed CSV files.
4. The platform will install from `requirements.txt`; subsequent pushes to the same branch redeploy automatically.

## Data storage
- All washes are persisted inside `data/car_washes.csv`, which is versioned with the project.
- Each entry stores an auto-incremented ID, the wash date, and the fixed $40 price used for savings comparisons.

## Configuration
- Membership start date (used to determine how many $79.99 billing cycles have been charged) is defined in `streamlit_app.py` via the `MEMBERSHIP_START_DATE` constant. Update it if the subscription begins on a different day.
