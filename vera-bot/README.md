# Vera Bot — magicpin AI Challenge

An intelligent, trigger-driven merchant engagement bot for WhatsApp, designed to maximize merchant engagement, avoid spam fatigue, and deliver personalized commercial impact for local businesses.

---

## 📁 Project Architecture

```
vera-bot/
├── main.py             # FastAPI entrypoint exposing the 5 official endpoints
├── composer.py         # Multi-provider LLM caller + prompt routing
├── rules.py            # Fast-path intent detection, auto-reply backoff & guardrails
├── templates.py        # High-scoring fact-grounded templates for all triggers
├── storage.py          # Context store, versioning, suppressions & conversation memory
├── requirements.txt    # Python dependencies
├── README.md           # Documentation
└── data/               # Persistent caches and data seeds
```

---

## ⚡ Core Highlights

1. **Trigger-Kind-Aware Prompt Routing**:
   - Tailored message formulation for all 10+ trigger kinds (e.g. `research_digest`, `perf_spike`, `perf_dip`, `recall_due`, `category_trend_movement`).
2. **Category Voice & Honorifics**:
   - Clinicians/Dentists addressed with "Dr." prefix and peer-to-peer clinical framing.
   - Salons, Cafes, and Gyms personalized to owner first name and practical trade dynamics.
3. **Fact-Grounded Specificity**:
   - Zero hallucination — anchors on verified numbers, citation sources, and YoY search trends.
4. **Fast-Path Intent Engine**:
   - **Auto-Reply Loop Buster**: Detects canned CRM bot messages ("thank you for contacting..."), applies 4h backoff, and automatically terminates on repeats.
   - **Hostile & Hard-Stop Opt-Out**: Instantly ends conversation on opt-outs ("stop", "unsubscribe", "not interested").
   - **Instant Action Switching**: When merchant commits ("yes", "ok let's do it"), switches immediately to action mode with prepared draft (no repetitive qualifying questions).

---

## 🚀 Setup & Run

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional LLM Key)
Create a `.env` file or export your key:
```bash
export OPENAI_API_KEY="sk-..."
# or
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export GEMINI_API_KEY="AIza..."
```
*Note: If no API key is set, Vera Bot operates with high-scoring deterministic fallback templates.*

### 3. Start the Server
```bash
python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

---

## 📡 Official Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/healthz` | Uptime and loaded context counts |
| `GET` | `/v1/metadata` | Team info, active model, and approach |
| `POST` | `/v1/context` | Ingests category, merchant, customer, or trigger data with versioning |
| `POST` | `/v1/tick` | Evaluates pending triggers and returns engagement actions |
| `POST` | `/v1/reply` | Evaluates incoming merchant messages and determines next turn action |
| `POST` | `/v1/teardown`| Flushes contexts and resets state between evaluation scenarios |

---

## 🧪 Testing with Judge Simulator

From the repository root:
```bash
# Run warmup and health tests
python3 judge_simulator.py --scenario warmup

# Run auto-reply test
python3 judge_simulator.py --scenario auto_reply_hell

# Run intent commitment test
python3 judge_simulator.py --scenario intent_transition

# Run hostile handling test
python3 judge_simulator.py --scenario hostile

# Run all test suites
python3 judge_simulator.py --scenario all
```
