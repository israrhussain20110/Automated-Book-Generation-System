# Kickstart AI: Automated Book Generation System

This project is a modular, scalable automation system designed to generate complete books using Large Language Models (LLMs). It features a robust Python backend with a human-in-the-loop CLI, a FastAPI REST interface, and a modern React (Vite) dashboard for a complete end-to-end experience.

## Features

- **Input + Outline Generation**: Takes a title and optional editor notes to generate a structured book outline.
- **Human-in-the-Loop Gating**: Pauses at critical junctures (outline approval, chapter generation) to receive human feedback or regeneration requests.
- **Context Chaining**: Preserves narrative consistency by feeding summaries of previous chapters into the LLM when writing the next chapter.
- **Dual Interfaces**: 
  - **Interactive CLI**: Simulates an `n8n` pipeline running in the terminal with step-by-step pauses and real-time alerts.
  - **Web Dashboard**: A premium, full-featured UI for managing book generations visually.
- **Multi-channel Notifications**: Built-in support for MS Teams Webhooks and SMTP Email alerts.
- **Multiple Databases**: Interface supports both local SQLite (default) and remote Supabase via simple CLI flags.
- **Mock Mode Fallback**: Can safely run demonstrations without an API key by returning placeholder text.

## Tech Stack
- **Backend**: Python 3.10+, FastAPI
- **Frontend**: Vite, React, TailwindCSS, Framer Motion
- **Database**: SQLite (built-in), Supabase (optional)
- **LLM**: Google Gemini
- **Document Output**: `python-docx`

---

## 1. Installation 

Clone the repository and install the dependencies:

```bash
# Backend Dependencies
pip install -r requirements.txt

# Frontend Dependencies
cd frontend
npm install
cd ..
```

---

## 2. Configuration (`.env`)

The project uses `python-dotenv` for managing credentials. Create a `.env` file in the root directory (you can copy `.env.example`) and configure the following:

```env
# AI Model Configuration
GOOGLE_API_KEY="your_google_gemini_api_key_here"

# Database Configuration (Optional, defaults to local SQLite if not provided)
SUPABASE_URL="https://your-project-url.supabase.co"
SUPABASE_KEY="your-supabase-anon-key"

# Notifications (Optional)
TEAMS_WEBHOOK_URL="https://your-teams-webhook-url"

# Email Configuration (for SMTP notifications)
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="your_email@gmail.com"
SMTP_PASS="your_app_password"
```

*Note: If `GOOGLE_API_KEY` is omitted, the system will run in **MOCK mode** to demonstrate the workflow without incurring costs or hitting rate limits.*

---

## 3. Usage: The Web Dashboard (Recommended)

To run the full stack with the visual dashboard:

1. **Start the FastAPI Backend**:
   ```bash
   python3 api.py
   ```
2. **Start the React Frontend** (in a new terminal):
   ```bash
   cd frontend
   npm run dev
   ```
3. Open `http://localhost:5173` in your browser.

From the dashboard, you can enter a title, review the outline, watch real-time chapter generation progress, and download the final `.docx` copy.

---

## 4. Usage: Interactive CLI (n8n Simulation)

You can run the full automation pipeline directly from the terminal, keeping the human editor in the loop.

```bash
python3 main.py --title "The Future of AI" --interactive --mode full
```

### CLI Arguments:
- `--title`: (Required) The title of the book.
- `--notes`: (Optional) Initial instructions for the LLM before generating the outline.
- `--interactive`: Enables the human-in-the-loop pauses for outline approval and chapter regeneration notes.
- `--mode`: `[outline|chapter|compile|full]` Run a specific stage or the whole pipeline (default is `full`).
- `--db`: `[sqlite|supabase]` Switch database engines dynamically.

**Example CLI Output flow:**
1. Generates Outline.
2. Triggers Email/Teams Webhook: *"Outline for 'The Future of AI' is ready..."*
3. Pauses Terminal: `[HUMAN REVIEW] Approve outline? [yes/no/no_notes_needed]:`
4. If approved, generates Chapters one-by-one, pausing for approval before each.
5. Compiles final draft and saves to `outputs/The_Future_of_AI.docx`.

---

## Project Structure

```text
book_gen_system/
├── core/               # DB, LLM, Research, Notifier Modules
├── stages/             # Logic for Outline, Chapter, and Compilation
├── data/               # Local persistence (SQLite DBs)
├── outputs/            # Generated Final Drafts (.docx)
├── frontend/           # Vite + React Dashboard App
├── api.py              # FastAPI Web Server
├── main.py             # Main CLI Orchestrator
├── requirements.txt    # Python dependencies
└── .env                # Environment Configurations
```
