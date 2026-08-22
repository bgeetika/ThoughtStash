# 🧠 ThoughtStash — Voice Thought Capture with 3-Agent Swarm

> **Think aloud on walks. Let an autonomous AI agent swarm remember, connect, and resurface your thoughts.**

ThoughtStash is a voice-first thought capture tool designed for walks, commutes, and hands-free moments. Powered by a **3-agent collaborative swarm**, it transcribes your voice, structures thoughts with deep metadata, autonomously identifies emerging themes and contradictions across time, and injects your thought history directly into interactive AI sessions.

---

## 🤖 Meet the Agent Swarm

```
🎙️ User Voice
      │
      ▼
┌──────────────────┐
│  🖊️ SCRIBE AGENT │ ──► Transcribes audio, removes fillers, structures thought
└─────────┬────────┘     (topics, entities, mood, key insights, urgency, questions)
          │
          ├───────────────────────────────┐
          ▼                               ▼ (async background task)
┌──────────────────┐            ┌─────────────────────┐
│  💾 SQLITE STORE │ ◄───────── │ 🔗 CONNECTOR AGENT  │ (AUTONOMOUS)
└─────────┬────────┘            └─────────────────────┘
          │                      - Compares against historical thoughts
          │                      - Finds cross-session connections & contradictions
          ▼                      - Surfaces proactive insights to UI
┌──────────────────┐
│  🔮 ORACLE AGENT │ ──► Context-aware RAG chat partner referencing your thought history
└──────────────────┘
```

| Agent | Responsibility | Execution Model |
|:---|:---|:---|
| 🖊️ **Scribe** | Accurate transcription, filler word removal, deep structuring (thought type, mood, urgency, implicit questions) | Event-driven (on audio upload) |
| 🔗 **Connector** | Cross-thought pattern recognition, contradiction detection, trend evolution tracking, proactive insights | **Autonomous** (runs automatically in the background after every thought) |
| 🔮 **Oracle** | Conversational partner equipped with RAG over your thought archive and Connector insights | On-demand (interactive chat) |

---

## ✨ Core Features

- 🎙️ **Frictionless Voice Capture** — Hands-free audio recording with live waveform and visual timer
- 📝 **Intelligent Structuring** — Converts rambles into crisp summaries, categorized tags, detected sentiment, and actionable insights
- 🔗 **Autonomous Connections** — The Connector agent alerts you in real-time when a new thought connects to or contradicts something you said days or weeks ago
- 🔍 **Semantic Search** — Vector similarity retrieval using `text-embedding-004`
- 📊 **Thought Pattern Analysis** — Comprehensive reporting across recurring themes, mood trajectories, and thinking evolution
- 💬 **Context-Aware Thinking Partner** — Ask "What have I been thinking about lately?" and the Oracle synthesizes your thoughts with exact timestamps and context

---

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/bgeetika/ThoughtStash.git
cd ThoughtStash

# 2. Set your Gemini API key (or use Vertex AI)
export GEMINI_API_KEY="your-gemini-api-key"

# 3. Launch the server
chmod +x start.sh
./start.sh
```

Open your browser at **`http://localhost:8877`** (or `http://<hostname>:8877` if hosting remotely).

---

## 🔑 Configuration

| Env Variable | Description | Required | Default |
|:---|:---|:---|:---|
| `GEMINI_API_KEY` | Google AI Studio API key | Yes* | - |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (for Vertex AI) | Yes* | - |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI region | No | `us-central1` |
| `GEMINI_MODEL` | Gemini model for agents | No | `gemini-2.0-flash` |
| `PORT` | Server port | No | `8877` |

*\*Provide either `GEMINI_API_KEY` or `GOOGLE_CLOUD_PROJECT`.*

---

## 📁 Project Structure

```
ThoughtStash/
├── app.py              # FastAPI server & async agent orchestration
├── agents.py           # Multi-agent definitions (Scribe, Connector, Oracle)
├── db.py               # SQLite persistence layer & connection store
├── requirements.txt    # Python dependencies (google-genai, google-adk, fastapi, etc.)
├── start.sh            # Automated startup script (venv + install + run)
├── static/
│   ├── index.html      # Modern SPA frontend with live Agent Status bar
│   ├── style.css       # Clean dark-mode UI with animated indicators
│   └── app.js          # Audio recording, real-time agent polling, chat RAG UI
└── data/               # Created at runtime (git-ignored)
    ├── mindtrail.db    # SQLite database with vector embeddings
    └── audio/          # Stored raw audio recordings
```

---

## 💡 The Vision

Most AI memory solutions focus on what *happened to you* (emails, meeting transcripts, browser history). **ThoughtStash** captures what you *thought about* — the walking epiphanies, shower thoughts, and evolving intuitions. It provides the missing **write-side memory layer for long-horizon personal AI agents**.

---

## 📄 License

MIT
