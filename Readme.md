# MyEdMaster — Legal Chatbot

A legal advice chatbot for business and education topics, powered by the Groq API. Includes PDF generation for legal documents.

## Project Structure

```
├── backend/
│   ├── ai_core.py      # Groq API calls + memory store
│   ├── app.py           # Flask server (JSON API + serves frontend)
│   └── pdf_gen.py       # PDF document generation (fpdf2)
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── bootstrap.py         # One-time setup script
├── requirements.txt
└── .gitignore
```

## Setup

### Prerequisites

- Python 3.10 or newer
- A Groq API key (get one at https://console.groq.com)

### 1. Clone the repo

```bash
git clone <repo-url>
cd Capstone
```

### 2. Create the virtual environment and install dependencies

```bash
python bootstrap.py
```

This creates a `.venv` folder and installs everything from `requirements.txt`.

### 3. Create a `.env` file in the project root

```
GROQ_API_KEY=your_api_key_here
```

Replace `your_api_key_here` with your actual Groq API key.

## Running

```bash
# Windows
.venv\Scripts\python.exe backend/app.py

# macOS / Linux
.venv/bin/python backend/app.py
```

Open http://127.0.0.1:5000 in your browser.

## Features

- Chat with an AI legal advisor on business and education topics
- Multiple chat sessions with history sidebar
- Generate PDF legal documents (toggle the document icon in the input bar)
- Dark / light mode toggle

## Dependencies

| Package | Purpose |
|---|---|
| flask | Web server and API |
| requests | HTTP calls to Groq API |
| python-dotenv | Load `.env` variables |
| fpdf2 | PDF document generation |

## Debugging

To see user messages and bot replies printed in the terminal, open `backend/app.py` and set:

```python
DEBUG_LOG = True
```
