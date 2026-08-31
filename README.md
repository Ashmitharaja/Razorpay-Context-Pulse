# Razorpay Context Pulse

Razorpay Context Pulse is an automated payment recovery engine that captures failed payment webhooks, evaluates failure context using Google Gemini, generates payment recovery links, and dispatches customer notifications.

## Features

* **Webhook Handling**: FastAPI server (`uvicorn`) designed to listen for incoming Razorpay payment failure webhooks.
* **AI-Driven Context Evaluation**: Integrates Google Gemini (`gemini-3.6-flash`) for failure analysis with a rule-engine fallback.
* **Native Recovery Links**: Automatically generates payment links via the Razorpay API upon detecting failure events.
* **Notification Dispatch**: Sends recovery SMS messages via Twilio and native Razorpay notification channels.
* **Local Metrics & Logging**: Records event metrics and status logs to a local SQLite database (`contextpulse.db`).

## Tech Stack

* **Language**: Python 3.12+
* **Framework**: FastAPI, Uvicorn
* **Integrations**: Razorpay SDK, Google GenAI SDK, Twilio SDK
* **Database**: SQLite

## Project Structure

```text
razorpay-contextpulse/
├── src/
│   ├── webhook_server.py    # FastAPI application entrypoint and endpoints
│   ├── orchestrator.py      # Core business logic, Gemini AI, Razorpay & Twilio integration
│   ├── db.py                # SQLite database management
│   └── models.py            # Pydantic data models
├── .env.example             # Template for required environment variables
├── requirements.txt         # Project dependencies
└── README.md                # Project documentation

```

## Setup & Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Ashmitharaja/Razorpay-Context-Pulse.git
cd Razorpay-Context-Pulse

```

### 2. Set Up Virtual Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

```

### 3. Install Dependencies

```bash
pip install -r requirements.txt

```

### 4. Configure Environment Variables

Create a `.env` file in the root directory based on `.env.example`:

```env
RAZORPAY_KEY_ID=rzp_test_YOUR_KEY_ID
RAZORPAY_KEY_SECRET=YOUR_KEY_SECRET
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
TWILIO_ACCOUNT_SID=YOUR_TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN=YOUR_TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER=YOUR_TWILIO_PHONE_NUMBER

```

## Running the Application

Start the FastAPI server using Uvicorn:

```bash
uvicorn src.webhook_server:app --reload --port 8000

```

The server will start at `[http://127.0.0.1:8000](http://127.0.0.1:8000)`.

### Endpoints

* `POST /webhook/razorpay`: Endpoint to handle incoming payment failure webhooks.
* `GET /metrics`: Dashboard metrics and logged recovery events.
* `POST /simulate/payment-failed`: Test endpoint to trigger a simulated payment failure workflow.

## License

This project is open-source and available under the [MIT License](https://www.google.com/search?q=LICENSE).
<img width="1911" height="981" alt="image" src="https://github.com/user-attachments/assets/f4aa30a4-9084-47a4-8bce-cd94eb52b634" />
<img width="1944" height="975" alt="image" src="https://github.com/user-attachments/assets/c9e0a1ce-2982-439c-8a69-03fb373c6cbc" />
<img width="632" height="1125" alt="image" src="https://github.com/user-attachments/assets/e7b70d86-ad15-48dd-b1b3-dea307b311f9" />
<img width="2000" height="1003" alt="image" src="https://github.com/user-attachments/assets/56a9e54c-c446-4a00-b53c-62eec0744eee" />
<img width="546" height="803" alt="image" src="https://github.com/user-attachments/assets/84b4883d-7bb2-49c4-957c-4d7cb407658b" />
<img width="2000" height="925" alt="image" src="https://github.com/user-attachments/assets/ead30b67-ea38-4b73-ba13-dda7648873c2" />


