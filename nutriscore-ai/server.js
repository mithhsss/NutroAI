const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const cors = require('cors');
const { GoogleGenerativeAI } = require('@google/generative-ai');
require('dotenv').config();

const app = express();
const port = 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static('public'));

// Database Setup
const db = new sqlite3.Database('./nutriscore.db', (err) => {
    if (err) {
        console.error('Error connecting to database:', err.message);
    } else {
        console.log('Connected to the SQLite database.');
        initDb();
    }
});

function initDb() {
    db.serialize(() => {
        // Create Users Table
        db.run(`CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )`);

        // Create UserProfile Table
        db.run(`CREATE TABLE IF NOT EXISTS UserProfile (
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
        )`);

        // Create FoodLogs Table
        db.run(`CREATE TABLE IF NOT EXISTS FoodLogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            food_name TEXT,
            score INTEGER,
            date TEXT,
            FOREIGN KEY (user_id) REFERENCES Users(id)
        )`);
    });
}

// Gemini API Setup
let genAI = null;
if (process.env.GEMINI_API_KEY) {
    genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
}

// ---- API Routes ----

// Signup
app.post('/api/signup', (req, res) => {
    const { name, email, password } = req.body;
    db.run('INSERT INTO Users (name, email, password) VALUES (?, ?, ?)', [name, email, password], function(err) {
        if (err) {
            return res.status(400).json({ error: err.message });
        }
        res.json({ userId: this.lastID });
    });
});

// Login
app.post('/api/login', (req, res) => {
    const { email, password } = req.body;
    db.get('SELECT * FROM Users WHERE email = ? AND password = ?', [email, password], (err, row) => {
        if (err) return res.status(500).json({ error: err.message });
        if (!row) return res.status(401).json({ error: 'Invalid email or password' });

        const userId = row.id;
        // Check if user has a profile
        db.get('SELECT * FROM UserProfile WHERE user_id = ?', [userId], (err, profileRow) => {
            if (err) return res.status(500).json({ error: err.message });
            res.json({
                userId: userId,
                needsProfile: !profileRow
            });
        });
    });
});

// Save Profile
app.post('/api/profile', (req, res) => {
    const {
        userId, age, gender, height, weight, diet_preference,
        allergies, fitness_goal, activity_level, sugar_level,
        sleep_hours, water_intake, medical_conditions
    } = req.body;

    const query = `
        INSERT INTO UserProfile 
        (user_id, age, gender, height, weight, diet_preference, allergies, fitness_goal, activity_level, sugar_level, sleep_hours, water_intake, medical_conditions) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `;
    const params = [
        userId, age, gender, height, weight, diet_preference, allergies,
        fitness_goal, activity_level, sugar_level, sleep_hours, water_intake, medical_conditions
    ];

    db.run(query, params, function(err) {
        if (err) return res.status(400).json({ error: err.message });
        res.json({ success: true });
    });
});

// Get User Dashboard Data
app.get('/api/dashboard/:id', (req, res) => {
    const userId = req.params.id;
    let data = { user: null, profile: null, logs: [], healthScore: 50 };

    db.get('SELECT name, email FROM Users WHERE id = ?', [userId], (err, user) => {
        if (err || !user) return res.status(404).json({ error: 'User not found' });
        data.user = user;

        db.get('SELECT * FROM UserProfile WHERE user_id = ?', [userId], (err, profile) => {
            if (profile) data.profile = profile;

            db.all('SELECT * FROM FoodLogs WHERE user_id = ? ORDER BY id DESC', [userId], (err, logs) => {
                if (logs) {
                    data.logs = logs;
                    // Calculate a simple health score based on food logs (start at 50, clamp 0-100)
                    let score = 50;
                    logs.forEach(log => {
                        score += (log.score - 50) * 0.2; // Example logic, score > 50 increases health score
                    });
                    data.healthScore = Math.min(Math.max(Math.round(score), 0), 100);
                }
                res.json(data);
            });
        });
    });
});

// Log Food
app.post('/api/logs/:id', (req, res) => {
    const userId = req.params.id;
    const { food_name, score } = req.body;
    const date = new Date().toISOString().split('T')[0];

    db.run('INSERT INTO FoodLogs (user_id, food_name, score, date) VALUES (?, ?, ?, ?)', [userId, food_name, score, date], function(err) {
        if (err) return res.status(400).json({ error: err.message });
        res.json({ success: true, logId: this.lastID });
    });
});

// Analyze Food Label with Gemini
app.post('/api/analyze', async (req, res) => {
    const { labelText } = req.body;

    if (!genAI) {
        return res.status(500).json({ error: 'Gemini API is not configured. Add GEMINI_API_KEY to .env file.' });
    }

    try {
        const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });
        const prompt = \`
Analyze the following food label ingredients and nutritional information:
"\${labelText}"

Determine:
1. Is it Healthy, Moderately Healthy, or Unhealthy?
2. Give it a score from 0 to 100 (100 being healthiest).
3. Provide a short explanation (2-3 sentences).

Return the response STRICTLY as a JSON object, like this:
{
  "status": "Healthy / Moderately Healthy / Unhealthy",
  "score": 85,
  "explanation": "This food is... "
}
\`;
        
        const result = await model.generateContent(prompt);
        const responseText = result.response.text();
        
        // Extract JSON from the response text (handling markdown code blocks if any)
        const jsonMatch = responseText.match(/\\{.*\\}/s);
        if (jsonMatch) {
            const parsedData = JSON.parse(jsonMatch[0]);
            res.json(parsedData);
        } else {
            console.log("Raw Gemini Response:", responseText);
            res.status(500).json({ error: 'Failed to parse Gemini API response' });
        }

    } catch (error) {
        console.error('Error calling Gemini API:', error);
        res.status(500).json({ error: 'Failed to analyze label' });
    }
});

app.listen(port, () => {
    console.log(\`NutriScore AI server running at http://localhost:\${port}\`);
});
