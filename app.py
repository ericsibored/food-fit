from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DB_PATH = INSTANCE_DIR / "food_fit.db"

app = Flask(__name__)


def get_connection() -> sqlite3.Connection:
    INSTANCE_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS weights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL UNIQUE,
                weight REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                target_weight REAL
            )
            """
        )


init_db()


def fetch_target_weight() -> float | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT target_weight FROM user_settings WHERE id = 1"
        ).fetchone()
    if row is None:
        return None
    return row["target_weight"]


@app.route("/")
def index() -> str:
    week_start = _get_week_start()
    week_days = [week_start + timedelta(days=offset) for offset in range(7)]
    week_start_iso = week_start.isoformat()
    week_end_iso = (week_start + timedelta(days=6)).isoformat()

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT entry_date, weight FROM weights ORDER BY entry_date"
        ).fetchall()
        meal_rows = connection.execute(
            """
            SELECT id, entry_date, meal_type, food_name, calories, protein, fat, sugars, carbs
            FROM meal_items
            WHERE entry_date BETWEEN ? AND ?
            ORDER BY entry_date, meal_type, id
            """,
            (week_start_iso, week_end_iso),
        ).fetchall()

    weights = [{"date": row["entry_date"], "weight": row["weight"]} for row in rows]
    meal_items = [_row_to_meal_item(row) for row in meal_rows]
    items_by_day_meal = _group_meal_items(meal_items)

    week_payload = []
    for day in week_days:
        day_iso = day.isoformat()
        meals = []
        daily_items = []
        for meal_key, meal_label in MEAL_TYPES:
            items = items_by_day_meal.get((day_iso, meal_key), [])
            daily_items.extend(items)
            meals.append(
                {
                    "key": meal_key,
                    "label": meal_label,
                    "items": items,
                    "totals": _totals_for_items(items),
                }
            )
        week_payload.append(
            {
                "date": day_iso,
                "label": day.strftime("%a, %b %d"),
                "meals": meals,
                "daily_totals": _totals_for_items(daily_items),
            }
        )

    return render_template(
        "index.html",
        weights=weights,
        today=date.today().isoformat(),
        target_weight=fetch_target_weight(),
    )


@app.route("/weights", methods=["POST"])
def add_weight() -> str:
    entry_date = request.form.get("entry_date", "").strip()
    weight_value = request.form.get("weight", "").strip()

    if not entry_date or not weight_value:
        return redirect(url_for("index"))

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO weights (entry_date, weight)
            VALUES (?, ?)
            ON CONFLICT(entry_date)
            DO UPDATE SET weight = excluded.weight
            """,
            (entry_date, float(weight_value)),
        )

    return redirect(url_for("index"))


@app.route("/target-weight", methods=["POST"])
def set_target_weight() -> str:
    target_weight = request.form.get("target_weight", "").strip()

    if not target_weight:
        return redirect(url_for("index"))

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO user_settings (id, target_weight)
            VALUES (1, ?)
            ON CONFLICT(id)
            DO UPDATE SET target_weight = excluded.target_weight
            """,
            (float(target_weight),),
        )

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
