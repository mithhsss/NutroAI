# NutriScore AI

NutriScore AI is a simple web application that provides personalized food recommendations and analyzes packaged food labels. It tracks your daily food intake and health score.

## Tech Stack

- Frontend: HTML, CSS, JavaScript, Bootstrap
- Backend: Node.js, Express
- Database: SQLite
- AI Integration: Google Gemini API

## Prerequisites

- Node.js installed

## How to Run

1. Navigate to the project directory: `cd nutriscore-ai`
2. Install dependencies: `npm install`
3. Create a `.env` file in the root directory and add your Gemini API Key:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```
4. Start the server: `node server.js`
5. Open your browser and go to `http://localhost:3000`

## Features

- User Authentication (Login / Signup)
- Health Profiling (12-question health assessment)
- Dashboard tracking health score and previous food logs
- AI-Powered Food Label Analysis using Gemini
- Food Recommendations (fruits, salads, healthy snacks)
