from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Optional, Tuple

import gspread
import pandas as pd
import streamlit as st


MEMBERSHIP_MONTHLY_COST = 79.99
PAY_PER_WASH = 40.00
MEMBERSHIP_START_DATE = date(2025, 9, 25)
DEFAULT_WORKSHEET_NAME = "car_washes"
HEADER_ROW = ["date", "price"]
SERVICE_ACCOUNT_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"
SHEET_ID_ENV = "GOOGLE_SHEET_ID"


@dataclass
class CycleStats:
    wash_count: int
    membership_cost: float
    a_la_carte_cost: float

    @property
    def savings(self) -> float:
        return self.a_la_carte_cost - self.membership_cost


@dataclass
class OverallStats(CycleStats):
    cycles_elapsed: int
    cycles_recorded: int


class SheetConfigError(RuntimeError):
    """Raised when Google Sheets is not configured correctly."""


def _service_account_info() -> Optional[Dict[str, Any]]:
    if "gcp_service_account" in st.secrets:
        secret_dict = st.secrets["gcp_service_account"]
        return {key: secret_dict[key] for key in secret_dict}

    env_json = os.getenv(SERVICE_ACCOUNT_ENV)
    if env_json:
        return json.loads(env_json)
    return None


def _sheet_id() -> Optional[str]:
    return st.secrets.get("google_sheet_id") or os.getenv(SHEET_ID_ENV)


def _worksheet_name() -> str:
    return st.secrets.get("google_worksheet_name", DEFAULT_WORKSHEET_NAME)


def _ensure_header(worksheet: gspread.Worksheet) -> None:
    header = [cell.lower() for cell in worksheet.row_values(1)]
    if header[: len(HEADER_ROW)] != HEADER_ROW:
        # Normalize header to expected columns without IDs.
        worksheet.update("A1:B1", [HEADER_ROW])


def _worksheet() -> gspread.Worksheet:
    creds = _service_account_info()
    if not creds:
        raise SheetConfigError(
            "Missing Google service account credentials. "
            "Add a `gcp_service_account` block to `.streamlit/secrets.toml` "
            "or set the GOOGLE_SERVICE_ACCOUNT_JSON environment variable."
        )

    sheet_id = _sheet_id()
    if not sheet_id:
        raise SheetConfigError(
            "Missing Google Sheet ID. Provide `google_sheet_id` in secrets "
            "or set the GOOGLE_SHEET_ID environment variable."
        )

    worksheet_name = _worksheet_name()
    try:
        client = gspread.service_account_from_dict(creds)
        spreadsheet = client.open_by_key(sheet_id)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=100, cols=3)
        _ensure_header(worksheet)
        return worksheet
    except gspread.SpreadsheetNotFound as exc:
        raise SheetConfigError(
            "Unable to open the Google Sheet. Confirm the Sheet ID is correct "
            "and that it is shared with the service account email."
        ) from exc
    except Exception as exc:
        raise SheetConfigError(f"Google Sheets error: {exc}") from exc


@st.cache_data(ttl=60)
def load_washes() -> pd.DataFrame:
    """Fetch all car wash entries from Google Sheets."""
    worksheet = _worksheet()
    records = worksheet.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=HEADER_ROW)

    df = df.rename(columns=str.lower)
    df = df[[col for col in HEADER_ROW if col in df.columns]]
    df["price"] = df["price"].astype(float)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date")


def has_entry_for(day: date, df: pd.DataFrame) -> bool:
    """Check if an entry already exists for the specified day."""
    if df.empty:
        return False
    return bool((df["date"] == day).any())


def append_wash(day: date, df: pd.DataFrame) -> bool:
    """
    Append a wash for the provided day.

    Returns True if a new wash was written, False if it already exists.
    """
    if has_entry_for(day, df):
        return False

    worksheet = _worksheet()
    worksheet.append_row(
        [day.isoformat(), f"{PAY_PER_WASH:.2f}"],
        value_input_option="USER_ENTERED",
    )
    load_washes.clear()
    return True


def add_months(base: date, months: int) -> date:
    """Return ``base`` advanced by ``months`` months (day preserved)."""
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, base.day)


def cycle_start_for(day: date) -> date:
    """Return the membership billing cycle start date that contains ``day``."""
    if day < MEMBERSHIP_START_DATE:
        return MEMBERSHIP_START_DATE
    months_diff = (day.year - MEMBERSHIP_START_DATE.year) * 12 + (
        day.month - MEMBERSHIP_START_DATE.month
    )
    if day.day < MEMBERSHIP_START_DATE.day:
        months_diff -= 1
    months_diff = max(months_diff, 0)
    return add_months(MEMBERSHIP_START_DATE, months_diff)


def cycle_label(start: date) -> str:
    """Human-readable inclusive date range for a billing cycle."""
    end = add_months(start, 1) - timedelta(days=1)
    return f"{start:%b %d, %Y} – {end:%b %d, %Y}"


def compute_cycle_stats(df: pd.DataFrame) -> Dict[date, CycleStats]:
    """Compute per-billing-cycle statistics keyed by cycle start date."""
    if df.empty:
        return {}

    working = df.copy()
    working["cycle_start"] = working["date"].apply(cycle_start_for)

    summaries: Dict[date, CycleStats] = {}
    for start, group in working.groupby("cycle_start"):
        wash_count = int(len(group))
        a_la_carte = wash_count * PAY_PER_WASH
        summaries[start] = CycleStats(
            wash_count=wash_count,
            membership_cost=MEMBERSHIP_MONTHLY_COST,
            a_la_carte_cost=a_la_carte,
        )
    return dict(sorted(summaries.items(), key=lambda item: item[0], reverse=True))


def membership_cycles_elapsed(as_of: date) -> int:
    """Number of billing cycles charged between the start date and ``as_of``."""
    if as_of < MEMBERSHIP_START_DATE:
        return 0
    months_diff = (as_of.year - MEMBERSHIP_START_DATE.year) * 12 + (
        as_of.month - MEMBERSHIP_START_DATE.month
    )
    cycles = months_diff + (1 if as_of.day >= MEMBERSHIP_START_DATE.day else 0)
    return max(cycles, 1)


def compute_overall_stats(df: pd.DataFrame, as_of: date) -> OverallStats:
    """Aggregate savings across every recorded billing cycle."""
    cycles_elapsed = membership_cycles_elapsed(as_of)
    total_membership = cycles_elapsed * MEMBERSHIP_MONTHLY_COST
    total_a_la_carte = len(df) * PAY_PER_WASH
    cycle_stats = compute_cycle_stats(df)
    return OverallStats(
        wash_count=int(len(df)),
        membership_cost=total_membership,
        a_la_carte_cost=total_a_la_carte,
        cycles_elapsed=cycles_elapsed,
        cycles_recorded=len(cycle_stats),
    )


def format_currency(amount: float) -> str:
    return f"${amount:,.2f}"


def days_until_next_renewal(today: date) -> Tuple[date, int]:
    """Return the next renewal date and remaining days until it arrives."""
    this_month_renewal = today.replace(day=25)
    if today <= this_month_renewal:
        next_renewal = this_month_renewal
    else:
        if today.month == 12:
            next_renewal = date(today.year + 1, 1, 25)
        else:
            next_renewal = date(today.year, today.month + 1, 25)
    delta_days = (next_renewal - today).days
    return next_renewal, delta_days


def render_membership_summary(df: pd.DataFrame, today: date) -> None:
    """Render top-level membership insights."""
    next_renewal, days_remaining = days_until_next_renewal(today)
    totals = compute_overall_stats(df, today)

    col1, col2, col3 = st.columns(3)
    col1.metric("Monthly membership", format_currency(MEMBERSHIP_MONTHLY_COST))
    col2.metric(
        "Next renewal",
        next_renewal.strftime("%b %d, %Y"),
        f"in {days_remaining} day{'s' if days_remaining != 1 else ''}",
    )
    col3.metric("Total savings so far", format_currency(totals.savings))


def filter_cycle(df: pd.DataFrame, cycle_start: date | None) -> pd.DataFrame:
    if cycle_start is None:
        return df
    cycle_end = add_months(cycle_start, 1)
    mask = (df["date"] >= cycle_start) & (df["date"] < cycle_end)
    return df.loc[mask].copy()


def render_savings_filter(df: pd.DataFrame, today: date) -> pd.DataFrame:
    """Render a selector to inspect savings per billing cycle and return filtered rows."""
    summaries = compute_cycle_stats(df)
    st.subheader("Savings Breakdown")

    if not summaries:
        st.info("Log at least one car wash to unlock month-by-month savings.")
        return df

    options = ["All recorded cycles"]
    option_map: Dict[str, date] = {}
    for start in summaries.keys():
        label = cycle_label(start)
        options.append(label)
        option_map[label] = start

    selection = st.selectbox("Filter by billing cycle", options, index=0)
    if selection == "All recorded cycles":
        stats = compute_overall_stats(df, today)
        membership_cost = stats.membership_cost
        wash_count = stats.wash_count
        a_la_carte = stats.a_la_carte_cost
        savings = stats.savings
        context = f"{stats.cycles_elapsed} billing cycle(s)"
        filtered_df = df
    else:
        start = option_map[selection]
        stats = summaries[start]
        membership_cost = stats.membership_cost
        wash_count = stats.wash_count
        a_la_carte = stats.a_la_carte_cost
        savings = stats.savings
        context = selection
        filtered_df = filter_cycle(df, start)

    metrics = st.columns(4)
    metrics[0].metric("Washes logged", wash_count, context)
    metrics[1].metric("Pay-per-wash cost", format_currency(a_la_carte))
    metrics[2].metric("Membership cost", format_currency(membership_cost))
    metrics[3].metric("Savings", format_currency(savings))

    return filtered_df


def render_history(df: pd.DataFrame) -> None:
    """Display the most recent wash and a table of historical logs."""
    st.subheader("Car Wash History")
    if df.empty:
        st.info("No car washes recorded yet.")
        return

    most_recent = df.sort_values("date", ascending=False).iloc[0]
    st.success(
        f"Last wash: {most_recent['date'].strftime('%B %d, %Y')} "
        f"({format_currency(most_recent['price'])})"
    )
    display_df = df.copy()[["date", "price"]].sort_values("date", ascending=False)
    display_df["date"] = pd.to_datetime(display_df["date"]).dt.strftime("%B %d, %Y")
    display_df["price"] = display_df["price"].map(format_currency)
    st.dataframe(
        display_df.rename(columns={"date": "Date", "price": "Included price"}),
        use_container_width=True,
        hide_index=True,
    )


def main() -> None:
    st.set_page_config(page_title="Car Wash Tracker", page_icon="🚗", layout="wide")
    st.title("Car Wash Membership Tracker")
    st.write(
        "Track every wash included in your \\$79.99 monthly membership and instantly "
        "see the savings compared to paying \\$40 per visit."
    )

    try:
        df = load_washes()
    except SheetConfigError as exc:
        st.error(exc)
        st.info(
            "Configure the Google Sheets backend by following the README instructions "
            "for service accounts and `st.secrets`."
        )
        st.stop()

    today = date.today()

    render_membership_summary(df, today)

    pin_secret = st.secrets.get("log_pin")
    button_col = st.columns([1, 1, 1])[1]
    already_logged = has_entry_for(today, df)
    button_label = "Log today's car wash" if not already_logged else "Already logged today"

    with button_col:
        pin_input = st.text_input(
            "Enter PIN to log today's wash",
            type="password",
            max_chars=4,
            key="log_pin_input",
            disabled=already_logged or pin_secret is None,
            help="Enter the 4-digit PIN configured in Streamlit secrets.",
        )
        if pin_input and not pin_input.isdigit():
            st.warning("PIN must contain digits only.")
        if st.button(
            button_label,
            use_container_width=True,
            disabled=already_logged or pin_secret is None,
        ):
            try:
                if pin_secret is None:
                    st.error("Logging PIN not configured. Set `log_pin` in secrets.")
                elif not pin_input or not pin_input.isdigit():
                    st.error("Enter a numeric PIN to continue.")
                elif pin_input != str(pin_secret):
                    st.error("Incorrect PIN. Try again.")
                elif append_wash(today, df):
                    st.toast("Logged today's car wash! ✅")
                    st.rerun()
                else:
                    st.warning("Today's wash is already recorded.")
            except SheetConfigError as exc:
                st.error(exc)

    filtered_df = render_savings_filter(df, today)
    render_history(filtered_df)


if __name__ == "__main__":
    main()

