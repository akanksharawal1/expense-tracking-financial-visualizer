from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FloatField, SelectField, DateField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal
from io import StringIO
import pymysql
import csv
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Database Function part is start from here
def get_db():
    #
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'),
        charset=os.getenv('DB_CHARSET'),
        cursorclass=pymysql.cursors.DictCursor
    )

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])

class TransactionForm(FlaskForm):
    amount = FloatField('Amount', validators=[DataRequired()])
    category = SelectField('Category', choices=[], validators=[DataRequired()])
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    description = StringField('Description', validators=[Length(max=100)])

class BudgetForm(FlaskForm):
    category = SelectField('Category', choices=[], validators=[DataRequired()])
    amount = FloatField('Budget Amount', validators=[DataRequired()])
    month_year = StringField('Month-Year (YYYY-MM)', validators=[DataRequired(), Length(min=7, max=7)])

# Routes part from here, as you can see
@app.route('/')
def home():
    return redirect(url_for('dashboard') if 'user_id' in session else 'login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (form.email.data,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], form.password.data):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('You are now logged in.', 'success')
            return redirect(url_for('dashboard'))
        flash('Incorrect email or password. Please try again.', 'danger')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        conn = get_db()
        cursor = conn.cursor()
        hashed_pw = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        try:
            cursor.execute('INSERT INTO users (username, email, password) VALUES (%s, %s, %s)',
                           (form.username.data, form.email.data, hashed_pw))
            conn.commit()
            flash('Account created! You can now log in.', 'success')
            return redirect(url_for('login'))
        except pymysql.IntegrityError:
            flash('This email is already registered. Try logging in.', 'danger')
        finally:
            conn.close()
    return render_template('register.html', form=form)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT SUM(amount) AS total FROM transactions WHERE user_id=%s AND type="income"', (session['user_id'],))
    income = cursor.fetchone()['total'] or 0

    cursor.execute('SELECT SUM(amount) AS total FROM transactions WHERE user_id=%s AND type="expense"', (session['user_id'],))
    expense = abs(cursor.fetchone()['total'] or 0)

    cursor.execute('SELECT category, SUM(amount) AS total FROM transactions WHERE user_id=%s AND type="expense" GROUP BY category', (session['user_id'],))
    category_data = cursor.fetchall()

    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute("""
        SELECT b.category, b.amount AS budget, SUM(t.amount) AS spent
        FROM budgets b
        LEFT JOIN transactions t ON b.category = t.category
        AND t.user_id = b.user_id AND t.type = 'expense'
        AND DATE_FORMAT(t.date, '%%Y-%%m') = b.month_year
        WHERE b.user_id = %s AND b.month_year = %s
        GROUP BY b.category, b.amount
    """, (session['user_id'], current_month))

    alerts = []
    for row in cursor.fetchall():
        spent = float(row['spent'] or 0)
        budget = float(row['budget'])
        if spent >= budget:
            alerts.append(f"You have exceeded your budget limit for '{row['category']}' this month. You spent ₹{spent:.2f} against ₹{budget:.2f}.")
        elif spent >= 0.8 * budget:
            alerts.append(f"You are close to your budget limit for '{row['category']}'. You used ₹{spent:.2f} of ₹{budget:.2f}.")

    conn.close()
    return render_template('dashboard.html', income=income, expense=expense, balance=income-expense, expense_by_category=category_data, budget_alerts=alerts)

@app.route('/transactions', methods=['GET', 'POST'])
def manage_transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    form = TransactionForm()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM categories')
    form.category.choices = [(c['name'], c['name']) for c in cursor.fetchall()]

    if form.validate_on_submit():
        transaction_type = 'expense' if form.amount.data < 0 else 'income'
        cursor.execute('INSERT INTO transactions (user_id, amount, category, date, description, type) VALUES (%s, %s, %s, %s, %s, %s)',
                       (session['user_id'], form.amount.data, form.category.data, form.date.data, form.description.data, transaction_type))
        conn.commit()
        conn.close()
        flash('Transaction recorded successfully.', 'success')
        return redirect(url_for('manage_transactions'))

    cursor.execute('SELECT * FROM transactions WHERE user_id = %s ORDER BY date DESC', (session['user_id'],))
    records = cursor.fetchall()
    conn.close()
    return render_template('transactions.html', form=form, transactions=records)

@app.route('/delete_transaction/<int:id>')
def delete_transaction(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM transactions WHERE id = %s AND user_id = %s', (id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Transaction deleted.', 'success')
    return redirect(url_for('manage_transactions'))

@app.route('/budgets', methods=['GET', 'POST'])
def manage_budgets():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    form = BudgetForm()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM categories')
    form.category.choices = [(c['name'], c['name']) for c in cursor.fetchall()]

    if form.validate_on_submit():
        try:
            datetime.strptime(form.month_year.data, '%Y-%m')
        except ValueError:
            flash('Invalid month format. Please use YYYY-MM.', 'danger')
            return render_template('budgets.html', form=form, budgets=[])

        cursor.execute('SELECT id FROM budgets WHERE user_id = %s AND category = %s AND month_year = %s',
                       (session['user_id'], form.category.data, form.month_year.data))
        existing = cursor.fetchone()

        if existing:
            cursor.execute('UPDATE budgets SET amount = %s WHERE id = %s', (form.amount.data, existing['id']))
            flash('Budget updated.', 'success')
        else:
            cursor.execute('INSERT INTO budgets (user_id, category, amount, month_year) VALUES (%s, %s, %s, %s)',
                           (session['user_id'], form.category.data, form.amount.data, form.month_year.data))
            flash('New budget added.', 'success')

        conn.commit()
        conn.close()
        return redirect(url_for('manage_budgets'))

    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute("""
        SELECT b.category, b.amount AS budget, b.month_year, ABS(SUM(t.amount)) AS spent
        FROM budgets b
        LEFT JOIN transactions t ON b.category = t.category
        AND t.user_id = b.user_id AND t.type = 'expense'
        AND DATE_FORMAT(t.date, '%%Y-%%m') = b.month_year
        WHERE b.user_id = %s
        GROUP BY b.category, b.amount, b.month_year
    """, (session['user_id'],))
    budgets = cursor.fetchall()
    conn.close()
    return render_template('budgets.html', form=form, budgets=budgets, current_month=current_month)

@app.route('/export')
def export_transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM transactions WHERE user_id = %s', (session['user_id'],))
    rows = cursor.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Amount (INR)', 'Category', 'Date', 'Description', 'Type'])

    for row in rows:
        writer.writerow([row['id'], f'₹{row["amount"]:.2f}', row['category'], row['date'], row['description'], row['type']])

    output.seek(0)
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename=transactions.csv'
    }

# Okay, you can logout from here, bye
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out. See you again!', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
