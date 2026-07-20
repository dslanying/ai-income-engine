# Deployment Guide - AI Income Engine

## Option A: Render.com (Recommended - Free, Auto HTTPS)

### Prerequisites
- GitHub account (free)

### Steps
1. Go to https://github.com/new and create a new repository (e.g., `ai-income-engine`)
2. Upload this project to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/ai-income-engine.git
   git push -u origin main
   ```
3. Go to https://dashboard.render.com/ and sign up with GitHub
4. Click "New Web Service" → Connect your GitHub repo
5. Render auto-detects Python. Set:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add Environment Variables in Render Dashboard:
   - Copy all values from your `.env` file
   - `APP_URL` should be your Render domain (e.g., `https://ai-income-engine.onrender.com`)
7. Click Deploy

### Update LemonSqueezy Webhook
After deployment, update the webhook URL in LemonSqueezy to your new Render domain + `/webhook`.

---

## Option B: PythonAnywhere (No GitHub needed, works in China)

### Steps
1. Go to https://www.pythonanywhere.com/ and create a free account
2. Open a Bash console and clone or upload your code
3. Create a virtual environment and install dependencies
4. Go to Web tab → Add a new web app → Manual configuration → Python 3.10
5. In the WSGI file, configure it to point to your FastAPI app
6. Set environment variables in the WSGI file
7. Reload the web app

---

## Important Notes
- The `.env` file contains secrets (API keys). Never commit it to GitHub.
- SQLite database will be created on the server. On Render free tier, the filesystem is ephemeral (data may be lost on restart). For production, switch to PostgreSQL.
- After deployment, update `APP_URL` and LemonSqueezy webhook to match your new domain.
