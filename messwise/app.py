from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

ROOT = Path(__file__).resolve().parent
DB = ROOT / "mess.db"
MEALS = ("Breakfast", "Lunch", "Snacks", "Dinner")
RECIPES = {"Breakfast": {"Rice": 0, "Dal": 0, "Vegetables": 0}, "Lunch": {"Rice": 0.15, "Dal": 0.10, "Vegetables": 0.12}, "Snacks": {"Rice": 0, "Dal": 0, "Vegetables": 0}, "Dinner": {"Rice": 0.15, "Dal": 0.10, "Vegetables": 0.12}}
app = Flask(__name__)
app.secret_key = "change-this-before-deployment"


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY, student TEXT NOT NULL, meal_date TEXT NOT NULL,
            meal TEXT NOT NULL, attending INTEGER NOT NULL,
            UNIQUE(student, meal_date, meal));
        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY, meal_date TEXT NOT NULL, meal TEXT NOT NULL,
            attendance INTEGER NOT NULL, prepared REAL NOT NULL DEFAULT 0,
            consumed REAL NOT NULL DEFAULT 0, leftovers REAL NOT NULL DEFAULT 0,
            UNIQUE(meal_date, meal));
        CREATE TABLE IF NOT EXISTS forecasts (
            meal_date TEXT NOT NULL, meal TEXT NOT NULL,
            predicted INTEGER NOT NULL, registrations INTEGER NOT NULL,
            historical REAL, created_at TEXT NOT NULL,
            PRIMARY KEY(meal_date, meal));
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO settings VALUES ('capacity', '500');
        INSERT OR IGNORE INTO settings VALUES ('buffer', '0.05');
        """)


def prediction(db, day, meal):
    registrations = db.execute("SELECT COUNT(*) n FROM registrations WHERE meal_date=? AND meal=? AND attending=1", (day, meal)).fetchone()["n"]
    prior = db.execute("SELECT attendance FROM outcomes WHERE meal=? AND meal_date<? ORDER BY meal_date DESC LIMIT 28", (meal, day)).fetchall()
    historical = sum(r["attendance"] for r in prior) / len(prior) if prior else None
    # Blend registration count with a recent attendance baseline. With no history,
    # registration count is the transparent cold-start estimate.
    estimate = round(0.8 * registrations + 0.2 * historical) if historical is not None and registrations else (round(historical) if historical is not None else registrations)
    capacity = int(db.execute("SELECT value FROM settings WHERE key='capacity'").fetchone()[0])
    return min(capacity, max(0, estimate)), registrations, historical


def save_forecast_snapshot(db, day, meal):
    """Freeze the current forecast once, preserving the pre-service estimate."""
    existing = db.execute(
        "SELECT 1 FROM forecasts WHERE meal_date=? AND meal=?", (day, meal)
    ).fetchone()
    if existing:
        return False
    predicted, registrations, historical = prediction(db, day, meal)
    db.execute(
        "INSERT INTO forecasts(meal_date, meal, predicted, registrations, historical, created_at) "
        "VALUES(?,?,?,?,?,?)",
        (day, meal, predicted, registrations, historical, datetime.now().isoformat(timespec="seconds")),
    )
    return True


@app.route("/")
def dashboard():
    init_db()
    day = request.args.get("date", date.today().isoformat())
    with connect() as db:
        cards = []
        for meal in MEALS:
            snapshot = db.execute(
                "SELECT predicted, registrations, historical FROM forecasts WHERE meal_date=? AND meal=?",
                (day, meal),
            ).fetchone()
            if snapshot:
                pred, regs, hist = snapshot["predicted"], snapshot["registrations"], snapshot["historical"]
            else:
                pred, regs, hist = prediction(db, day, meal)
            outcome = db.execute("SELECT * FROM outcomes WHERE meal_date=? AND meal=?", (day, meal)).fetchone()
            cards.append({"meal": meal, "predicted": pred, "registered": regs, "historical": round(hist) if hist is not None else None, "snapshot_saved": snapshot is not None, "outcome": outcome, "ingredients": {k: round(pred*v, 1) for k, v in RECIPES[meal].items() if v}})
        totals = db.execute("SELECT COALESCE(SUM(leftovers),0) waste, COALESCE(SUM(attendance),0) served FROM outcomes WHERE meal_date=?", (day,)).fetchone()
        history = db.execute("SELECT meal_date, SUM(attendance) attendance, SUM(leftovers) leftovers FROM outcomes WHERE meal_date>=? GROUP BY meal_date ORDER BY meal_date", ((date.fromisoformat(day)-timedelta(days=6)).isoformat(),)).fetchall()
        performance = db.execute("""
            SELECT AVG(ABS(o.attendance - f.predicted)) mae, COUNT(*) forecast_count
            FROM outcomes o JOIN forecasts f
              ON f.meal_date=o.meal_date AND f.meal=o.meal
        """).fetchone()
    return render_template(
        "dashboard.html", day=day, cards=cards, totals=totals,
        history=history, mae=round(performance["mae"], 1) if performance["mae"] is not None else None,
        forecast_count=performance["forecast_count"],
    )


@app.route("/forecast", methods=["POST"])
def lock_forecasts():
    init_db()
    day = request.form.get("meal_date", "")
    try:
        date.fromisoformat(day)
    except ValueError:
        flash("Choose a valid service date before saving forecasts.", "error")
        return redirect(url_for("dashboard"))

    saved = 0
    with connect() as db:
        for meal in MEALS:
            completed = db.execute(
                "SELECT 1 FROM outcomes WHERE meal_date=? AND meal=?", (day, meal)
            ).fetchone()
            if not completed:
                saved += save_forecast_snapshot(db, day, meal)
    if saved:
        flash(f"Saved forecast snapshots for {saved} meal(s). These estimates are now frozen for this date.", "success")
    else:
        flash("No new forecasts saved. Snapshots already exist or those meals have been recorded.", "error")
    return redirect(url_for("dashboard", date=day))


@app.route("/waste-board")
def waste_board():
    init_db()
    today = date.today().isoformat()
    try:
        day = date.fromisoformat(request.args.get("date", today)).isoformat()
    except ValueError:
        day = today
    week_start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
    with connect() as db:
        daily = db.execute(
            "SELECT COALESCE(SUM(leftovers), 0) waste, COUNT(*) meals_logged "
            "FROM outcomes WHERE meal_date=?",
            (day,),
        ).fetchone()
        weekly_waste = db.execute(
            "SELECT COALESCE(SUM(leftovers), 0) waste FROM outcomes "
            "WHERE meal_date BETWEEN ? AND ?",
            (week_start, day),
        ).fetchone()["waste"]
        meal_rows = db.execute(
            "SELECT meal, leftovers FROM outcomes WHERE meal_date=? "
            "ORDER BY CASE meal WHEN 'Breakfast' THEN 1 WHEN 'Lunch' THEN 2 "
            "WHEN 'Snacks' THEN 3 WHEN 'Dinner' THEN 4 ELSE 5 END",
            (day,),
        ).fetchall()
    return render_template(
        "waste_board.html", day=day,
        day_label=date.fromisoformat(day).strftime("%A, %d %B %Y"),
        today_waste=daily["waste"], weekly_waste=weekly_waste,
        meals_logged=daily["meals_logged"], meal_rows=meal_rows,
        total_meals=len(MEALS),
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    init_db()
    if request.method == "POST":
        student = request.form.get("student", "").strip()
        day = request.form.get("meal_date", "")
        if not student or not day:
            flash("Enter your name or student ID and select a date.", "error")
        elif day < date.today().isoformat():
            flash("Registrations for past dates are closed.", "error")
        else:
            with connect() as db:
                for meal in MEALS:
                    db.execute("INSERT INTO registrations(student,meal_date,meal,attending) VALUES(?,?,?,?) ON CONFLICT(student,meal_date,meal) DO UPDATE SET attending=excluded.attending", (student, day, meal, int(meal in request.form.getlist("meals"))))
            flash("Meal choices saved. You can update them before the meal.", "success")
            return redirect(url_for("register", student=student, day=day))
    student = request.args.get("student", "")
    day = request.args.get("day", (date.today()+timedelta(days=1)).isoformat())
    selected = []
    if student:
        with connect() as db:
            selected = [r["meal"] for r in db.execute("SELECT meal FROM registrations WHERE student=? AND meal_date=? AND attending=1", (student, day))]
    return render_template("register.html", meals=MEALS, student=student, day=day, selected=selected)


@app.route("/record", methods=["POST"])
def record():
    init_db()
    day, meal = request.form["meal_date"], request.form["meal"]
    try:
        attendance = max(0, int(request.form["attendance"]))
        prepared, consumed, leftovers = (max(0, float(request.form.get(k, 0))) for k in ("prepared", "consumed", "leftovers"))
    except ValueError:
        flash("Enter valid non-negative numbers for the meal record.", "error")
        return redirect(url_for("dashboard", date=day))
    with connect() as db:
        db.execute("INSERT INTO outcomes(meal_date,meal,attendance,prepared,consumed,leftovers) VALUES(?,?,?,?,?,?) ON CONFLICT(meal_date,meal) DO UPDATE SET attendance=excluded.attendance,prepared=excluded.prepared,consumed=excluded.consumed,leftovers=excluded.leftovers", (day, meal, attendance, prepared, consumed, leftovers))
    flash(f"{meal} outcome saved.", "success")
    return redirect(url_for("dashboard", date=day))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
