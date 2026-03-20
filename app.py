from flask import Flask, render_template, request, redirect, url_for
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from collections import defaultdict
import json

app = Flask(__name__)

# MongoDB Connection
client = MongoClient("mongodb://localhost:27017/")
db = client["expense_tracker"]
users_collection    = db["users"]
expenses_collection = db["expenses"]


# ── Context processor: inject current_path for active nav ────────────────────
@app.context_processor
def inject_current_path():
    return {"current_path": request.path}


# ── Helper: build all chart + stats data ─────────────────────────────────────
def get_dashboard_data():
    expenses = list(expenses_collection.find())
    now = datetime.now()

    category_totals = defaultdict(int)
    monthly_totals  = defaultdict(int)
    total_amount    = 0
    monthly_this    = 0

    for exp in expenses:
        amt      = exp.get("amount", 0)
        cat      = exp.get("category", "Other")
        date_str = exp.get("date", "")

        category_totals[cat] += amt
        total_amount += amt

        if date_str:
            try:
                d   = datetime.strptime(date_str, "%Y-%m-%d")
                key = d.strftime("%Y-%m")
                monthly_totals[key] += amt
                if d.year == now.year and d.month == now.month:
                    monthly_this += amt
            except Exception:
                pass

    # Last 6 months labels + values
    from calendar import month_abbr
    month_labels, month_values = [], []
    for i in range(5, -1, -1):
        m   = (now.month - i - 1) % 12 + 1
        y   = now.year if now.month - i > 0 else now.year - 1
        key = f"{y}-{m:02d}"
        month_labels.append(f"{month_abbr[m]} {str(y)[-2:]}")
        month_values.append(monthly_totals.get(key, 0))

    avg_expense = round(total_amount / len(expenses)) if expenses else 0
    highest_cat = max(category_totals, key=category_totals.get) if category_totals else "—"

    # Recent 5 expenses (latest first)
    recent = sorted(
        [e for e in expenses if e.get("date")],
        key=lambda x: x["date"], reverse=True
    )[:5]

    return {
        "cat_labels":   json.dumps(list(category_totals.keys())),
        "cat_values":   json.dumps(list(category_totals.values())),
        "month_labels": json.dumps(month_labels),
        "month_values": json.dumps(month_values),
        "total_amount": total_amount,
        "monthly_this": monthly_this,
        "avg_expense":  avg_expense,
        "highest_cat":  highest_cat,
        "recent":       recent,
        "total_count":  len(expenses),
    }


# ── Home Page ─────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


# ── Register ──────────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        users_collection.insert_one({"username": username, "password": password})
        return render_template("success.html")
    return render_template("register.html")


# ── Login ─────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = users_collection.find_one({"username": username, "password": password})
        if user:
            data = get_dashboard_data()
            return render_template("dashboard.html", suggestion=None, **data)
        else:
            return render_template("error.html")
    return render_template("login.html")


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    data = get_dashboard_data()
    return render_template("dashboard.html", suggestion=None, **data)


# ── View Expenses ─────────────────────────────────────────────────────────────
@app.route("/view-expenses")
def view_expenses():
    expenses = list(expenses_collection.find())
    return render_template("view_expenses.html", expenses=expenses)


# ── Reports ───────────────────────────────────────────────────────────────────
@app.route("/reports")
def reports():
    expenses      = list(expenses_collection.find())
    monthly_total = 0
    yearly_total  = 0
    current_month = datetime.now().month
    current_year  = datetime.now().year

    # Category breakdown
    cat_totals = defaultdict(lambda: {"total": 0, "count": 0})
    grand_total = 0

    for exp in expenses:
        amt      = exp.get("amount", 0)
        cat      = exp.get("category", "Other")
        date_str = exp.get("date", "")
        cat_totals[cat]["total"] += amt
        cat_totals[cat]["count"] += 1
        grand_total += amt

        if date_str:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                if d.year == current_year:
                    yearly_total += amt
                if d.year == current_year and d.month == current_month:
                    monthly_total += amt
            except Exception:
                pass

    cat_data = []
    for name, vals in sorted(cat_totals.items(), key=lambda x: -x[1]["total"]):
        pct = round(vals["total"] / grand_total * 100) if grand_total else 0
        cat_data.append({"name": name, "total": vals["total"], "count": vals["count"], "pct": pct})

    return render_template(
        "reports.html",
        monthly_total=monthly_total,
        yearly_total=yearly_total,
        cat_data=cat_data
    )


# ── Add Expense Page ──────────────────────────────────────────────────────────
@app.route("/add-expense-page")
def add_expense_page():
    return render_template("add_expense.html")


# ── Add Expense (POST) ────────────────────────────────────────────────────────
@app.route("/add-expense", methods=["POST"])
def add_expense():
    amount   = int(request.form["amount"])
    category = request.form["category"]
    date     = request.form.get("date")
    note     = request.form.get("note", "")

    expenses_collection.insert_one({
        "amount": amount, "category": category, "date": date, "note": note
    })

    data        = get_dashboard_data()
    highest_cat = data["highest_cat"]

    if data["total_count"] == 0:
        return render_template("dashboard.html", suggestion="No expenses recorded yet.", **data)

    tips = {
        "Food":          "Try reducing outside food 🍔",
        "Shopping":      "Control shopping budget 🛍",
        "Travel":        "Consider cheaper transport 🚗",
        "Bills":         "Monitor electricity usage 💡",
        "Entertainment": "Limit entertainment spend 🎬",
    }
    suggestion  = f"You spend most on {highest_cat}. "
    suggestion += tips.get(highest_cat, "Track expenses carefully 📊")
    suggestion += f" | Avg expense: ₹{data['avg_expense']}"

    return render_template("dashboard.html", suggestion=suggestion, **data)


# ── Edit Expense (GET – show form) ────────────────────────────────────────────
@app.route("/edit-expense/<id>")
def edit_expense_page(id):
    expense = expenses_collection.find_one({"_id": ObjectId(id)})
    if not expense:
        return redirect(url_for("view_expenses"))
    return render_template("edit_expense.html", expense=expense)


# ── Edit Expense (POST – save changes) ───────────────────────────────────────
@app.route("/edit-expense/<id>", methods=["POST"])
def edit_expense(id):
    amount   = int(request.form["amount"])
    category = request.form["category"]
    date     = request.form.get("date")

    expenses_collection.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"amount": amount, "category": category, "date": date}}
    )
    return redirect(url_for("view_expenses"))


# ── Delete Expense ────────────────────────────────────────────────────────────
@app.route("/delete-expense/<id>")
def delete_expense(id):
    expenses_collection.delete_one({"_id": ObjectId(id)})
    return redirect(url_for("view_expenses"))


if __name__ == "__main__":
    app.run(debug=True)