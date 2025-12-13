# Local Testing Guide

To test the Tech Job Finder locally on your machine, follow these steps.

## 1. Setup Credentials

You need to add the following files to the root directory (`/Users/krkaushikkumar/Desktop/Job/`):

### A. Google Cloud Service Account (`service_account.json`)
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., "job-finder-local").
3. Enable **Google Sheets API**.
4. Go to **IAM & Admin** > **Service Accounts**.
5. Create a new Service Account.
6. Click "Keys" tab > "Add Key" > "Create new key" > **JSON**.
7. Save the downloaded file as `service_account.json` in the project root.
8. **IMPORTANT**: Open the `service_account.json`, copy the `client_email` address, and **Share your target Google Sheet** with that email (Editor access).

### B. Environment Variables (`.env`)
1. Rename `.env.example` to `.env` (if you haven't already).
2. Fill in the following keys in `.env`:

```bash
# Google (Point to the file you just created)
GOOGLE_APPLICATION_CREDENTIALS=service_account.json

# Google Sheets
SHEET_ID=your_google_sheet_id_here 
# (Get this from the URL: docs.google.com/spreadsheets/d/THIS_PART/edit)

# LLM Keys (Optional - only if you want AI Features)
GROQ_API_KEY=your_key
# ... other keys if used

# Notifications (Optional)
DISCORD_WEBHOOK_URL=your_discord_webhook
EMAIL_APP_PASSWORD=your_gmail_app_password
```

## 2. Configure Settings
Open `config/config.yaml.example` (or `config/config.yaml` if you copied it):
- Setup your keywords in `filters`.
- Set `enabled: false` for `gmail_ingest` if you don't want to mess with Gmail API yet.

## 3. Run Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies (if not already)
pip install -r requirements.txt

# Run the finder
python runner.py
```

## 4. Check Results
- Look at your Google Sheet.
- Check the terminal output for logs.
