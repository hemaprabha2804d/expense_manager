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
income_collection   = db["income"]  # 🔴 NEW: Income Collection


# ── Context processor: inject current_path for active nav ────────────────────
@app.context_processor
def inject_current_path():
    return {"current_path": request.path}


# ── Helper: build all chart + stats data ─────────────────────────────────────
def get_dashboard_data():
    expenses = list(expenses_collection.find())
    income   = list(income_collection.find())  # Fetch Income
    now = datetime.now()

    category_totals = defaultdict(int)
    monthly_totals  = defaultdict(int)
    
    # 🔴 Period aggregators
    cat_by_month = defaultdict(lambda: defaultdict(int))
    cat_by_year  = defaultdict(lambda: defaultdict(int))
    
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
                m_key = d.strftime("%Y-%m")
                y_key = d.strftime("%Y")
                monthly_totals[m_key] += amt
                
                # 🔴 Save categorized amounts
                cat_by_month[m_key][cat] += amt
                cat_by_year[y_key][cat] += amt
                
                if d.year == now.year and d.month == now.month:
                    monthly_this += amt
            except Exception:
                pass

    # Income Calculations
    total_income = sum(i.get("amount", 0) for i in income)
    net_balance  = total_income - total_amount

    # Available Periods sorted
    months_keys = sorted(list(cat_by_month.keys()), reverse=True)
    years_keys  = sorted(list(cat_by_year.keys()), reverse=True)

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
        "cat_by_month": json.dumps(cat_by_month),
        "cat_by_year":  json.dumps(cat_by_year), # 🔴 Added
        "months_keys":  months_keys,
        "years_keys":   years_keys,               # 🔴 Added
        "total_amount": total_amount,
        "monthly_this": monthly_this,
        "avg_expense":  avg_expense,
        "highest_cat":  highest_cat,
        "recent":       recent,
        "total_count":  len(expenses),
        "total_income": total_income,
        "net_balance":  net_balance
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
    income        = list(income_collection.find()) # 🔴 Fetch Income
    monthly_total = 0
    yearly_total  = 0
    monthly_income = 0 # 🔴 Monthly Income total
    yearly_income  = 0 # 🔴 Yearly Income total
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

    # 🔴 Income accounting for Reports
    for inc in income:
        amt = inc.get("amount", 0)
        date_str = inc.get("date", "")

        if date_str:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                if d.year == current_year:
                    yearly_income += amt
                if d.year == current_year and d.month == current_month:
                    monthly_income += amt
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
        monthly_income=monthly_income, # 🔴 Pass to View
        yearly_income=yearly_income,   # 🔴 Pass to View
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


# ── 🔴 NEW: Add Income Page ────────────────────────────────────────────────────
@app.route("/add-income-page")
def add_income_page():
    return render_template("add_income.html")


# ── 🔴 NEW: Add Income (POST) ──────────────────────────────────────────────────
@app.route("/add-income", methods=["POST"])
def add_income():
    amount = int(request.form["amount"])
    source = request.form["source"]  # Using "source" for income type
    date   = request.form.get("date")
    note   = request.form.get("note", "")

    income_collection.insert_one({
        "amount": amount, "source": source, "date": date, "note": note
    })

    data = get_dashboard_data()
    return render_template("dashboard.html", suggestion="Income Added Successfully!", **data)


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