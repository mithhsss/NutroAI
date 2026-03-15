from flask import Flask, request, jsonify, render_template
import sqlite3
import os
import google.generativeai as genai
from dotenv import load_dotenv
import json
import re
from datetime import date

load_dotenv()

app = Flask(__name__)

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

def get_db_connection():
    conn = sqlite3.connect('nutriscore.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Create Users Table
    conn.execute('''CREATE TABLE IF NOT EXISTS Users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')

    # Create UserProfile Table
    conn.execute('''CREATE TABLE IF NOT EXISTS UserProfile (
        user_id INTEGER PRIMARY KEY,
        age INTEGER,
        gender TEXT,
        height REAL,
        weight REAL,
        diet_preference TEXT,
        allergies TEXT,
        fitness_goal TEXT,
        activity_level TEXT,
        sugar_level TEXT,
        sleep_hours REAL,
        water_intake REAL,
        medical_conditions TEXT,
        FOREIGN KEY (user_id) REFERENCES Users(id)
    )''')

    # Create FoodLogs Table
    conn.execute('''CREATE TABLE IF NOT EXISTS FoodLogs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        food_name TEXT,
        score INTEGER,
        date TEXT,
        FOREIGN KEY (user_id) REFERENCES Users(id)
    )''')
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

# ---- Page Routes ---- #
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


# ---- API Routes ---- #
@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO Users (name, email, password) VALUES (?, ?, ?)', (name, email, password))
        conn.commit()
        userId = cur.lastrowid
        return jsonify({'userId': userId})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Email already exists'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM Users WHERE email = ? AND password = ?', (email, password)).fetchone()
    
    if user is None:
        conn.close()
        return jsonify({'error': 'Invalid email or password'}), 401
    
    userId = user['id']
    profileRow = conn.execute('SELECT * FROM UserProfile WHERE user_id = ?', (userId,)).fetchone()
    conn.close()
    
    return jsonify({
        'userId': userId,
        'needsProfile': profileRow is None
    })

@app.route('/api/profile', methods=['POST'])
def api_profile():
    data = request.get_json()
    
    query = '''
        INSERT INTO UserProfile 
        (user_id, age, gender, height, weight, diet_preference, allergies, fitness_goal, activity_level, sugar_level, sleep_hours, water_intake, medical_conditions) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    params = (
        data.get('userId'), data.get('age'), data.get('gender'), data.get('height'), data.get('weight'),
        data.get('diet_preference'), data.get('allergies'), data.get('fitness_goal'), data.get('activity_level'),
        data.get('sugar_level'), data.get('sleep_hours'), data.get('water_intake'), data.get('medical_conditions')
    )

    conn = get_db_connection()
    try:
        conn.execute(query, params)
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/dashboard/<int:user_id>', methods=['GET'])
def api_dashboard(user_id):
    conn = get_db_connection()
    data = {'user': None, 'profile': None, 'logs': [], 'healthScore': 50}
    
    user = conn.execute('SELECT name, email FROM Users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
        
    data['user'] = dict(user)
    
    profile = conn.execute('SELECT * FROM UserProfile WHERE user_id = ?', (user_id,)).fetchone()
    if profile:
        data['profile'] = dict(profile)
        
    logs = conn.execute('SELECT * FROM FoodLogs WHERE user_id = ? ORDER BY id DESC', (user_id,)).fetchall()
    
    if logs:
        data['logs'] = [dict(log) for log in logs]
        score = 50
        for log in logs:
            score += (log['score'] - 50) * 0.2
        data['healthScore'] = min(max(round(score), 0), 100)
        
    conn.close()
    return jsonify(data)

@app.route('/api/logs/<int:user_id>', methods=['POST'])
def api_logs(user_id):
    data = request.get_json()
    food_name = data.get('food_name')
    score = data.get('score')
    current_date = date.today().isoformat()

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO FoodLogs (user_id, food_name, score, date) VALUES (?, ?, ?, ?)', 
                    (user_id, food_name, score, current_date))
        conn.commit()
        return jsonify({'success': True, 'logId': cur.lastrowid})
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    finally:
        conn.close()

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    data = request.get_json()
    label_text = data.get('labelText', '')

    if not api_key:
        return jsonify({'error': 'Gemini API is not configured. Add GEMINI_API_KEY to .env file.'}), 500

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
Analyze the following food label ingredients and nutritional information:
"{label_text}"

Determine:
1. Is it Healthy, Moderately Healthy, or Unhealthy?
2. Give it a score from 0 to 100 (100 being healthiest).
3. Provide a short explanation (2-3 sentences).

Return the response STRICTLY as a JSON object, like this:
{{
  "status": "Healthy / Moderately Healthy / Unhealthy",
  "score": 85,
  "explanation": "This food is... "
}}
"""
        response = model.generate_content(prompt)
        response_text = response.text
        
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            parsed_data = json.loads(json_match.group(0))
            return jsonify(parsed_data)
        else:
            print("Raw Gemini Response:", response_text)
            return jsonify({'error': 'Failed to parse Gemini API response'}), 500

    except Exception as e:
        print('Error calling Gemini API:', e)
        return jsonify({'error': 'Failed to analyze label'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
