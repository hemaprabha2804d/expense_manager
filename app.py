from flask import Flask, render_template, request
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)

# MongoDB Connection
client = MongoClient("mongodb://localhost:27017/")
db = client["expense_tracker"]

users_collection = db["users"]
expenses_collection = db["expenses"]


# Home Page
@app.route("/")
def home():
    return render_template("index.html")


# Register Page
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        users_collection.insert_one({
            "username": username,
            "password": password
        })

        return render_template("success.html")

    return render_template("register.html")


# Login Page
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = users_collection.find_one({
            "username": username,
            "password": password
        })

        if user:
            return render_template("dashboard.html")
        else:
            return render_template("error.html")

    return render_template("login.html")


# Dashboard
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", suggestion=None)


# View Expenses
@app.route("/view-expenses")
def view_expenses():

    expenses = list(expenses_collection.find())

    return render_template(
        "view_expenses.html",
        expenses=expenses
    )


# Reports Page (Monthly & Yearly)
@app.route("/reports")
def reports():

    expenses = list(expenses_collection.find())

    monthly_total = 0
    yearly_total = 0

    current_month = datetime.now().month
    current_year = datetime.now().year

    for exp in expenses:

        # Skip records without date
        if "date" not in exp:
            continue

        expense_date = datetime.strptime(exp["date"], "%Y-%m-%d")

        if expense_date.year == current_year:
            yearly_total += exp["amount"]

        if expense_date.year == current_year and expense_date.month == current_month:
            monthly_total += exp["amount"]

    return render_template(
        "reports.html",
        monthly_total=monthly_total,
        yearly_total=yearly_total
    )


# Open Add Expense Page
@app.route("/add-expense-page")
def add_expense_page():
    return render_template("add_expense.html")


# Add Expense + AI Analysis
@app.route("/add-expense", methods=["POST"])
def add_expense():

    amount = int(request.form["amount"])
    category = request.form["category"]
    date = request.form.get("date")   # Safe get

    # Store Expense
    expenses_collection.insert_one({
        "amount": amount,
        "category": category,
        "date": date
    })

    expenses = list(expenses_collection.find())

    if not expenses:
        return render_template(
            "dashboard.html",
            suggestion="No expenses recorded yet."
        )

    category_totals = {}
    total_amount = 0

    for exp in expenses:

        cat = exp["category"]
        amt = exp["amount"]

        total_amount += amt

        if cat in category_totals:
            category_totals[cat] += amt
        else:
            category_totals[cat] = amt

    highest_category = max(category_totals, key=category_totals.get)
    highest_amount = category_totals[highest_category]

    avg_spending = total_amount / len(expenses)

    suggestion = f"You spend most on {highest_category} (₹{highest_amount}). "

    if highest_category == "Food":
        suggestion += "Try reducing outside food 🍔"

    elif highest_category == "Shopping":
        suggestion += "Control shopping budget 🛍"

    elif highest_category == "Travel":
        suggestion += "Consider cheaper transport 🚗"

    elif highest_category == "Bills":
        suggestion += "Monitor electricity usage 💡"

    else:
        suggestion += "Track expenses carefully 📊"

    suggestion += f" | Avg expense: ₹{int(avg_spending)}"

    return render_template(
        "dashboard.html",
        suggestion=suggestion
    )


if __name__ == "__main__":
    app.run(debug=True)