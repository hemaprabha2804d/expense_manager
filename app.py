from flask import Flask, render_template, request, redirect, url_for, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from collections import defaultdict
import json

app = Flask(__name__)
app.secret_key = "your_secret_key_change_this"  # Required for sessions

# MongoDB Connection
client = MongoClient("mongodb://localhost:27017/")
db = client["expense_tracker"]
users_collection    = db["users"]
expenses_collection = db["expenses"]
income_collection          = db["income"]          # 🔴 NEW: Income Collection
category_limits_collection = db["category_limits"]  # Per-category spending limits


# ── Context processor: inject current_path for active nav ────────────────────
@app.context_processor
def inject_current_path():
    return {"current_path": request.path}


# ── Helper: build all chart + stats data ─────────────────────────────────────
def get_dashboard_data():
    user_id = session.get("user_id")
    expenses = list(expenses_collection.find({"user_id": user_id}))
    income   = list(income_collection.find({"user_id": user_id}))  # Fetch Income
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

    # 🔴 Create Descriptive Period Labels
    from calendar import month_name
    month_options = []
    for k in months_keys:
        try:
            y, m = k.split("-")
            month_options.append({"key": k, "label": f"{month_name[int(m)]} {y}"})
        except: pass

    avg_expense = round(total_amount / len(expenses)) if expenses else 0
    highest_cat = max(category_totals, key=category_totals.get) if category_totals else "—"

    # Fetch per-category limits and compute warnings
    user_limits = {}
    limits_doc = category_limits_collection.find_one({"user_id": user_id})
    if limits_doc:
        user_limits = limits_doc.get("limits", {})

    limit_warnings = []
    for cat, limit_val in user_limits.items():
        spent = category_totals.get(cat, 0)
        pct   = round((spent / limit_val) * 100) if limit_val > 0 else 0
        limit_warnings.append({
            "category": cat,
            "spent":    spent,
            "limit":    limit_val,
            "pct":      min(pct, 100),
            "exceeded": spent > limit_val,
            "remaining": max(limit_val - spent, 0)
        })
    limit_warnings.sort(key=lambda x: (-int(x["exceeded"]), -x["pct"]))

    # Recent 5 expenses (latest first)
    recent = sorted(
        [e for e in expenses if e.get("date")],
        key=lambda x: x["date"], reverse=True
    )[:5]

    # Recent 5 income entries (latest first)
    recent_income = sorted(
        [i for i in income if i.get("date")],
        key=lambda x: x["date"], reverse=True
    )[:5]

    # Monthly income/expense for comparison chart (last 6 months)
    monthly_income_totals  = defaultdict(int)
    monthly_expense_totals = defaultdict(int)
    for inc in income:
        date_str = inc.get("date", "")
        if date_str:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                monthly_income_totals[d.strftime("%Y-%m")] += inc.get("amount", 0)
            except Exception:
                pass
    for exp in expenses:
        date_str = exp.get("date", "")
        if date_str:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                monthly_expense_totals[d.strftime("%Y-%m")] += exp.get("amount", 0)
            except Exception:
                pass
    all_months = sorted(set(list(monthly_income_totals.keys()) + list(monthly_expense_totals.keys())))[-6:]
    comparison_labels   = json.dumps(all_months)
    comparison_income   = json.dumps([monthly_income_totals.get(m, 0)  for m in all_months])
    comparison_expenses = json.dumps([monthly_expense_totals.get(m, 0) for m in all_months])

    return {
        "cat_labels":           json.dumps(list(category_totals.keys())),
        "cat_values":           json.dumps(list(category_totals.values())),
        "cat_by_month":         json.dumps(cat_by_month),
        "cat_by_year":          json.dumps(cat_by_year),
        "month_options":        month_options,
        "years_keys":           years_keys,
        "total_amount":         total_amount,
        "monthly_this":         monthly_this,
        "avg_expense":          avg_expense,
        "highest_cat":          highest_cat,
        "recent":               recent,
        "recent_income":        recent_income,
        "total_count":          len(expenses),
        "total_income":         total_income,
        "net_balance":          net_balance,
        "limit_warnings":       limit_warnings,
        "user_limits":          user_limits,
        "comparison_labels":    comparison_labels,
        "comparison_income":    comparison_income,
        "comparison_expenses":  comparison_expenses,
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
            session["user_id"] = str(user["_id"])  # Save user to session
            session["username"] = username
            data = get_dashboard_data()
            return render_template("dashboard.html", suggestion=None, **data)
        else:
            return render_template("error.html")
    return render_template("login.html")


# ── Logout ────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    data = get_dashboard_data()
    return render_template("dashboard.html", suggestion=None, **data)


# ── View Expenses ─────────────────────────────────────────────────────────────
@app.route("/view-expenses")
def view_expenses():
    user_id = session.get("user_id")
    expenses = list(expenses_collection.find({"user_id": user_id}))
    return render_template("view_expenses.html", expenses=expenses)


# ── Reports ───────────────────────────────────────────────────────────────────
@app.route("/reports")
def reports():
    user_id  = session.get("user_id")
    expenses = list(expenses_collection.find({"user_id": user_id}))
    income   = list(income_collection.find({"user_id": user_id}))  # Fetch Income
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
        "user_id": session.get("user_id"),
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


# ── Add Income Page ───────────────────────────────────────────────────────────
@app.route("/add-income-page")
def add_income_page():
    return render_template("add_income.html")


# ── View Income ────────────────────────────────────────────────────────────────
@app.route("/view-income")
def view_income():
    user_id = session.get("user_id")
    income  = list(income_collection.find({"user_id": user_id}).sort("date", -1))
    return render_template("view_income.html", income=income)


# ── Delete Income ──────────────────────────────────────────────────────────────
@app.route("/delete-income/<id>")
def delete_income(id):
    income_collection.delete_one({"_id": ObjectId(id)})
    return redirect(url_for("view_income"))


# ── Charts Page ────────────────────────────────────────────────────────────────
@app.route("/charts")
def charts_page():
    if "user_id" not in session:
        return redirect(url_for("login"))
    data = get_dashboard_data()
    return render_template("charts.html", **data)


# ── 🔴 NEW: Add Income (POST) ──────────────────────────────────────────────────
@app.route("/add-income", methods=["POST"])
def add_income():
    amount = int(request.form["amount"])
    source = request.form["source"]  # Using "source" for income type
    date   = request.form.get("date")
    note   = request.form.get("note", "")

    income_collection.insert_one({
        "user_id": session.get("user_id"),
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


# ── Set Category Limit ────────────────────────────────────────────────────────
@app.route("/set-category-limit", methods=["POST"])
def set_category_limit():
    user_id  = session.get("user_id")
    category = request.form.get("category")
    try:
        limit = int(request.form.get("limit", 0))
    except ValueError:
        limit = 0
    if user_id and category and limit > 0:
        category_limits_collection.update_one(
            {"user_id": user_id},
            {"$set": {f"limits.{category}": limit}},
            upsert=True
        )
    return redirect(url_for("dashboard"))


# ── Remove Category Limit ──────────────────────────────────────────────────────
@app.route("/remove-category-limit/<category>")
def remove_category_limit(category):
    user_id = session.get("user_id")
    if user_id:
        category_limits_collection.update_one(
            {"user_id": user_id},
            {"$unset": {f"limits.{category}": ""}}
        )
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)