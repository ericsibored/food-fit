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
            CREATE TABLE IF NOT EXISTS meal_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                meal_type TEXT NOT NULL,
                food_name TEXT NOT NULL,
                calories REAL,
                protein REAL,
                fat REAL,
                sugars REAL,
                carbs REAL
            )
            """
        )


MEAL_TYPES = [
    ("breakfast", "Breakfast"),
    ("lunch", "Lunch"),
    ("dinner", "Dinner"),
]


init_db()


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
        week_start=week_start_iso,
        prev_week=(week_start - timedelta(days=7)).isoformat(),
        next_week=(week_start + timedelta(days=7)).isoformat(),
        week_days=week_payload,
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


@app.route("/meal-items", methods=["POST"])
def add_meal_item() -> str:
    entry_date = request.form.get("entry_date", "").strip()
    meal_type = request.form.get("meal_type", "").strip()
    food_name = request.form.get("food_name", "").strip()
    week_start = request.form.get("week_start", "").strip()

    if not entry_date or not meal_type or not food_name:
        return redirect(url_for("index", week_start=week_start or None))

    calories = _parse_optional_float(request.form.get("calories"))
    protein = _parse_optional_float(request.form.get("protein"))
    fat = _parse_optional_float(request.form.get("fat"))
    sugars = _parse_optional_float(request.form.get("sugars"))
    carbs = _parse_optional_float(request.form.get("carbs"))

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO meal_items
                (entry_date, meal_type, food_name, calories, protein, fat, sugars, carbs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_date,
                meal_type,
                food_name,
                calories,
                protein,
                fat,
                sugars,
                carbs,
            ),
        )

    return redirect(url_for("index", week_start=week_start or None))


@app.route("/meal-items/<int:item_id>/delete", methods=["POST"])
def delete_meal_item(item_id: int) -> str:
    week_start = request.form.get("week_start", "").strip()
    with get_connection() as connection:
        connection.execute("DELETE FROM meal_items WHERE id = ?", (item_id,))
    return redirect(url_for("index", week_start=week_start or None))


def _get_week_start() -> date:
    week_start_param = request.args.get("week_start", "").strip()
    if week_start_param:
        try:
            selected_date = datetime.fromisoformat(week_start_param).date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()
    return selected_date - timedelta(days=selected_date.weekday())


def _parse_optional_float(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        return None
    return float(value)


def _row_to_meal_item(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "entry_date": row["entry_date"],
        "meal_type": row["meal_type"],
        "food_name": row["food_name"],
        "calories": row["calories"],
        "protein": row["protein"],
        "fat": row["fat"],
        "sugars": row["sugars"],
        "carbs": row["carbs"],
    }


def _group_meal_items(meal_items: list[dict]) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for item in meal_items:
        key = (item["entry_date"], item["meal_type"])
        grouped.setdefault(key, []).append(item)
    return grouped


def _totals_for_items(items: list[dict]) -> dict[str, float | None]:
    return {
        "calories": _sum_optional(items, "calories"),
        "protein": _sum_optional(items, "protein"),
        "fat": _sum_optional(items, "fat"),
        "sugars": _sum_optional(items, "sugars"),
        "carbs": _sum_optional(items, "carbs"),
    }


def _sum_optional(items: list[dict], field: str) -> float | None:
    values = [item[field] for item in items if item[field] is not None]
    return sum(values) if values else None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
