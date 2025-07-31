from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import main
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)  # for sessions

# Initialize database
def init_db():
    conn = sqlite3.connect('access_log.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    license_plate TEXT,
                    vehicle_type TEXT,
                    owner TEXT,
                    status TEXT,
                    timestamp TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS whitelist (
                    license_plate TEXT PRIMARY KEY,
                    vehicle_type TEXT,
                    owner TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

# === Admin Credentials (hardcoded for now) ===
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

# === Login Page ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USERNAME and request.form['password'] == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials!", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# === Protected Dashboard ===
@app.route('/')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    conn = sqlite3.connect('access_log.db')
    logs = conn.execute('SELECT * FROM access_log ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('dashboard.html', logs=logs)

@app.route('/admin')
def admin_panel():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    conn = sqlite3.connect('access_log.db')
    whitelist = conn.execute('SELECT * FROM whitelist').fetchall()
    conn.close()
    return render_template('admin.html', whitelist=whitelist) 

@app.route('/add_whitelist', methods=['POST'])
def add_whitelist():
    license_plate = request.form['license_plate'].upper()
    vehicle_type = request.form['vehicle_type']
    owner = request.form['owner']
    conn = sqlite3.connect('access_log.db')
    conn.execute('INSERT OR REPLACE INTO whitelist VALUES (?, ?, ?)', 
                 (license_plate, vehicle_type, owner))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/delete_whitelist/<plate>')
def delete_whitelist(plate):
    conn = sqlite3.connect('access_log.db')
    conn.execute('DELETE FROM whitelist WHERE license_plate=?', (plate,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/log_access', methods=['POST'])
def log_access():
    data = request.get_json()
    license_plate = data['plate'].upper()
    conn = sqlite3.connect('access_log.db')
    c = conn.cursor()
    c.execute('SELECT * FROM whitelist WHERE license_plate=?', (license_plate,))
    result = c.fetchone()
    if result:
        vehicle_type, owner = result[1], result[2]
        status = 'Authorized'
    else:
        vehicle_type, owner, status = '-', '-', 'Unauthorized'
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO access_log (license_plate, vehicle_type, owner, status, timestamp) VALUES (?, ?, ?, ?, ?)',
              (license_plate, vehicle_type, owner, status, timestamp))
    conn.commit()
    conn.close()
    return jsonify({'status': status})

if __name__ == '__main__':
    app.run(debug=True)


import requests
@app.route('/manual_gate', methods=['POST'])
def manual_gate():
    # Replace with your ESP32's actual IP address
    esp32_ip = "http://192.168.1.100"  # example IP ////////////////////////////////////////////////////////////////////////////////
    try:
        r = requests.get(f"{esp32_ip}/gate?manual=1", timeout=3)
        print("ESP32 Response:", r.text)
    except Exception as e:
        print("Error contacting ESP32:", e)

    # Log this action to access log as 'Manual'
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect('access_log.db')
    conn.execute('''INSERT INTO access_log (license_plate, vehicle_type, owner, status, timestamp)
                    VALUES (?, ?, ?, ?, ?)''',
                 ('-', '-', '-', 'Manual', timestamp))
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))
