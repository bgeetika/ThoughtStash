# 🧠 ThoughtStash — Voice Thought Capture

> **Think aloud on walks. Let AI remember, connect, and resurface your thoughts.**

ThoughtStash is a voice-first thought capture tool that lets you speak freely during walks/commutes. AI transcribes, structures, finds patterns across your thoughts over time, and feeds them back as persistent context for future model interactions.

## ✨ Features

- 🎙️ **Voice Capture** — Record thoughts via browser microphone
- 📝 **AI Structuring** — Gemini transcribes and extracts topics, entities, mood, key insights
- 🔍 **Semantic Search** — Find related thoughts via embeddings
- 🔗 **Pattern Recognition** — Discover recurring themes across weeks of thinking
- 💬 **Context-Aware Chat** — Chat with an AI that knows what you've been thinking about (RAG)

## 🏗️ Architecture

```
Voice Recording (Browser)
    │
    ▼ audio blob (webm)
FastAPI Backend (:8877)
    │
    ├─► Gemini API ──► Transcribe + Extract (topics, entities, mood, summary)
    │
    ├─► SQLite ──► Store thought + embedding
    │
    ├─► Pattern Engine ──► Gemini analyzes all thoughts for recurring themes
    │
    └─► Context Chat ──► RAG: retrieve relevant thoughts → inject into Gemini prompt
```

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/<your-username>/thoughtstash.git
cd thoughtstash

# 2. Set your Gemini API key
export GEMINI_API_KEY="your-key-here"

# 3. Run
chmod +x start.sh
./start.sh
```

The app will be available at `http://localhost:8877`

## 🔑 Configuration

| Env Variable | Description | Required |
|:---|:---|:---|
| `GEMINI_API_KEY` | Google AI Studio API key | Yes (or use Vertex AI) |
| `GOOGLE_CLOUD_PROJECT` | GCP project for Vertex AI | Alternative to API key |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI region (default: `us-central1`) | No |
| `GEMINI_MODEL` | Model name (default: `gemini-2.0-flash`) | No |
| `PORT` | Server port (default: `8877`) | No |

## 📁 Project Structure

```
thoughtstash/
├── app.py              # FastAPI backend (all routes)
├── db.py               # SQLite helpers
├── gemini_client.py    # Gemini API wrapper (transcription, patterns, chat)
├── requirements.txt    # Python dependencies
├── start.sh            # One-command launcher
├── static/
│   ├── index.html      # Single-page app
│   ├── style.css       # Dark-mode UI
│   └── app.js          # Frontend logic (voice recording, API calls)
└── data/               # Auto-created
    ├── mindtrail.db    # SQLite database
    └── audio/          # Saved audio files
```

## 🧪 Tech Stack

- **Backend:** Python + FastAPI
- **Frontend:** Vanilla HTML/CSS/JS
- **Database:** SQLite
- **AI:** Google Gemini API (`google-genai`)
- **Embeddings:** `text-embedding-004` for semantic search

## 🔮 Multi-Agent Roadmap (v2)

| Agent | Role |
|:---|:---|
| 🖊️ **Scribe** | Transcribe + clean audio |
| 🔗 **Connector** | Find patterns + connections across thoughts |
| 🔮 **Oracle** | Context-aware chat with RAG |

## 💡 The Vision

Most AI memory systems remember what *happened to you* (emails, meetings, docs). ThoughtStash remembers what you *thought about* — the walk epiphanies, the shower ideas, the evolving intuitions. It's the **write-side of long-horizon personal agents**.

## 📄 License

MIT
