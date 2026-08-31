```markdown
# Razorpay Context Pulse

Razorpay Context Pulse is an automated payment recovery engine that captures failed payment webhooks, evaluates transaction failure contexts using Google Gemini (with an automated rule-engine fallback), generates Razorpay payment recovery links, and dispatches automated notifications.

## Features

- **Webhook Handling**: FastAPI server (`uvicorn`) designed to listen for incoming Razorpay payment failure events.
- **AI-Driven Context Evaluation**: Integrates Google Gemini (`gemini-3.6-flash`) for failure analysis with an automatic fallback rule engine during API rate-limiting or quota exhaustion.
- **Native Recovery Links**: Automatically generates payment links via the Razorpay API upon detecting failed checkout attempts.
- **Notification Dispatch**: Sends recovery SMS messages via Twilio and native Razorpay channels.
- **Local Metrics & Logging**: Records event metrics to a local SQLite database (`contextpulse.db`).

## Tech Stack

- **Language**: Python 3.12+
- **Framework**: FastAPI, Uvicorn
- **Integrations**: Razorpay SDK, Google GenAI SDK, Twilio SDK
- **Database**: SQLite

## Project Structure

```text
razorpay-contextpulse/
├── src/
│   ├── webhook_server.py    # FastAPI application setup and endpoint handlers
│   ├── orchestrator.py      # Core logic for handling payment failures and AI analysis
│   └── database.py          # SQLite database connection and event logging
├── cancel_links.py          # Utility script to bulk-cancel active test payment links
├── requirements.txt         # Project dependencies
├── .gitignore               # Ignored files (.venv, .env, etc.)
└── README.md                # Project documentation

```

## Setup Instructions

### 1. Prerequisites

Ensure you have Python installed and set up a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

```

### 2. Install Dependencies

```powershell
pip install -r requirements.txt

```

### 3. Environment Configuration

Create a `.env` file in the root directory and add your secret keys:

```env
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
GEMINI_API_KEY=your_gemini_api_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number

```

### 4. Running the Webhook Server

Start the Uvicorn development server:

```powershell
uvicorn src.webhook_server:app --reload --port 8000

```

## Useful Tools

### Clear Test Payment Links

If you hit Razorpay's Test Mode limit for active links, execute the bulk-cancellation script:

```powershell
python cancel_links.py

```

```

```
