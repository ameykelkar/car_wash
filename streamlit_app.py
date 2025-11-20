from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
import streamlit as st


DATA_PATH = Path(__file__).parent / "data" / "car_washes.csv"
MEMBERSHIP_MONTHLY_COST = 79.99
PAY_PER_WASH = 40.00
MEMBERSHIP_START_DATE = date(2025, 9, 25)


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


def ensure_storage() -> None:
    """Make sure the CSV data store exists with the correct headers."""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        DATA_PATH.write_text("id,date,price\n", encoding="utf-8")


def load_washes() -> pd.DataFrame:
    """Return all car wash entries sorted by date."""
    ensure_storage()
    df = pd.read_csv(DATA_PATH)
    if df.empty:
        return pd.DataFrame(columns=["id", "date", "price"])
    df["id"] = df["id"].astype(int)
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

    next_id = int(df["id"].max()) + 1 if not df.empty else 1
    with DATA_PATH.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([next_id, day.isoformat(), f"{PAY_PER_WASH:.2f}"])
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


def render_savings_filter(df: pd.DataFrame, today: date) -> None:
    """Render a selector to inspect savings per billing cycle."""
    summaries = compute_cycle_stats(df)
    st.subheader("Savings Breakdown")

    if not summaries:
        st.info("Log at least one car wash to unlock month-by-month savings.")
        return

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
    else:
        start = option_map[selection]
        stats = summaries[start]
        membership_cost = stats.membership_cost
        wash_count = stats.wash_count
        a_la_carte = stats.a_la_carte_cost
        savings = stats.savings
        context = selection

    metrics = st.columns(4)
    metrics[0].metric("Washes logged", wash_count, context)
    metrics[1].metric("Pay-per-wash cost", format_currency(a_la_carte))
    metrics[2].metric("Membership cost", format_currency(membership_cost))
    metrics[3].metric("Savings", format_currency(savings))


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

    df = load_washes()
    today = date.today()

    render_membership_summary(df, today)

    button_col = st.columns([1, 1, 1])[1]
    already_logged = has_entry_for(today, df)
    button_label = "Log today's car wash" if not already_logged else "Already logged today"

    with button_col:
        if st.button(button_label, use_container_width=True, disabled=already_logged):
            if append_wash(today, df):
                st.toast("Logged today's car wash! ✅")
                st.rerun()
            else:
                st.warning("Today's wash is already recorded.")

    render_savings_filter(df, today)
    render_history(df)


if __name__ == "__main__":
    main()

