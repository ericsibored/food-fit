from __future__ import annotations

import sqlite3
from datetime import date
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


init_db()


@app.route("/")
def index() -> str:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT entry_date, weight FROM weights ORDER BY entry_date"
        ).fetchall()

    weights = [{"date": row["entry_date"], "weight": row["weight"]} for row in rows]

    return render_template(
        "index.html",
        weights=weights,
        today=date.today().isoformat(),
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
