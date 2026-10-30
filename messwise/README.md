# Messwise — Smart Mess Management

A pilot-ready Flask and SQLite prototype for student meal registration, meal demand planning, ingredient estimates, and kitchen actuals.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The SQLite database (`mess.db`) is created on first run.

## Prototype features

- Student signups for breakfast, lunch, snacks, and dinner, editable by re-submitting with the same name or ID.
- Meal forecasts blend today's signups with the latest 28 recorded attendances (80% signup, 20% history). Without history, signup count is used. Forecasts are capped at the configured 500-person capacity.
- Illustrative lunch and dinner ingredient rates: rice 150 g, dal 100 g, vegetables 120 g per forecast student. Replace these with measured kitchen rates before operational use.
- Admin entry for actual attendance, prepared, consumed, and leftover quantities.
- Daily overview and recent logged outcomes.
- Pre-service forecast snapshots: use “Save forecast snapshot” before a meal to freeze the estimate for that date. Later registrations do not change a saved estimate.
- Forecast MAE compares saved pre-service forecasts with actual attendance. Older outcomes without a saved forecast are excluded.
- Big-screen waste board at /waste-board: displays today's recorded leftovers, the last seven service days, and a meal-wise breakdown. It refreshes every minute and shows aggregate meal data only.

- Admin dashboard includes a seven-day waste chart; days without meal records are shown as missing data rather than zero waste.

## Notes

This is a local pilot, not a production deployment: there are no accounts or role-based access yet, and the default app secret and debug mode must be changed before hosting. The forecast is an explainable cold-start heuristic rather than a trained machine-learning model; collect enough meal history, then evaluate a proper baseline and regression models with a time-based holdout. Ingredient quantities are examples, not procurement instructions.
