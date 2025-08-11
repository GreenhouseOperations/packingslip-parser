# Render Deployment Guide

## Prerequisites
1. GitHub account with this repository pushed
2. Render account (free tier available)
3. Google Gemini API key

## Deployment Steps

### 1. Push to GitHub
```bash
git add .
git commit -m "Ready for Render deployment"
git push origin main
```

### 2. Create Render Service
1. Go to [render.com](https://render.com) and sign in
2. Click "New +" → "Web Service"
3. Connect your GitHub repository: `GreenhouseOperations/packingslip-parser`
4. Configure the service:
   - **Name**: `packingslip-parser`
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`

### 3. Environment Variables
In the Render dashboard, add these environment variables:
- `GEMINI_API_KEY`: Your Google Gemini API key
- `GEMINI_MODEL`: `gemini-2.0-flash-lite`
- `GEMINI_TEMPERATURE`: `0.1`

### 4. Deploy
- Click "Create Web Service"
- Wait for deployment (usually 2-5 minutes)
- Your app will be available at: `https://packingslip-parser.onrender.com`

## API Endpoints
- `POST /upload` - Upload PDF and get CSV
- `POST /test-ai` - Test AI extraction
- `GET /health` - Health check

## Frontend Integration
Update your React frontend to use the Render URL instead of localhost:5000

## Production Notes
- Free tier sleeps after 15 minutes of inactivity
- Paid tier ($7/month) keeps service always active
- CORS is enabled for all origins (configure for production security)

## Troubleshooting
- Check logs in Render dashboard
- Ensure all environment variables are set
- Verify GitHub repository is public or connected properly
