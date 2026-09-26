# 🌟 VeraForge — magicpin AI Challenge

> **Intelligent WhatsApp Merchant Engagement Bot ("Vera")**  
> Built for the magicpin AI Challenge to drive high-conversion, hyper-personalized merchant outreach without spam fatigue.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LLM Engine](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4.svg?style=flat&logo=google)](https://ai.google.dev/)
[![Judge Simulator](https://img.shields.io/badge/Evaluator-100%25%20Passing-success.svg?style=flat)]()

---

## 👥 Team Information

- **Team Name:** `VeraForge`
- **Team Member:** `Lav Rastogi`
- **Contact Email:** `lavrastogi01@gmail.com`
- **Model Engine:** `gemini-flash-latest` (with fast-path deterministic fallbacks)

---

## 🏗️ Architecture & Key Innovations

Vera is designed around a dual-engine architecture: a **Fast-Path Deterministic Rule & Guardrail Engine** combined with **Google Gemini LLM synthesis**.

```
magicpin-ai-challenge/
├── vera-bot/
│   ├── main.py             # FastAPI server with all 5 mandatory endpoints + teardown
│   ├── composer.py         # Multi-provider LLM caller (Gemini, OpenAI, Claude)
│   ├── rules.py            # Fast-path intent router, loop-breaker & safety guardrails
│   ├── templates.py        # Fact-grounded templates for all 25 seed triggers & categories
│   ├── storage.py          # Thread-safe in-memory context store with monotonic versioning
│   ├── requirements.txt    # Production dependencies
│   └── data/               # Persistent caches and data seeds
├── dataset/                # Challenge categories, merchants, customers & triggers
├── examples/               # API call examples and case studies
├── judge_simulator.py      # Official challenge evaluation simulator
├── render.yaml             # 1-click cloud deployment config for Render
└── README.md               # Main project documentation
```

### 🎯 Core Capabilities:

1. **Trigger-Kind-Aware Prompt Routing**:
   - Distinct logic tailored across all trigger types (`research_digest`, `perf_spike`, `perf_dip`, `recall_due`, `category_trend_movement`, etc.).
2. **Category Honorifics & Peer Framing**:
   - Clinical dentists addressed with `"Dr."` honorifics and clinical peer-to-peer framing.
   - Retail, cafes, gyms, and salons addressed with respectful local business tone (`"<Name> ji"` / owner first name).
3. **Fact-Grounded Specificity (Zero Hallucination)**:
   - Anchors strictly on verified context numbers (e.g. `+38%`, `₹1,240`, `14 appointments`, verified citations).
4. **Auto-Reply Loop Buster**:
   - Detects CRM bot auto-replies ("Thank you for reaching out...").
   - Implements 4-hour exponential backoff on Turn 1, and cleanly self-terminates (`action: "end"`) on repeat to prevent loops.
5. **Instant Action Switching**:
   - When a merchant commits ("Yes", "Ok let's do it", "Share draft"), immediately delivers the complete campaign draft without repetitive qualifying questions.
6. **Hostile & Hard-Stop Opt-Out**:
   - Immediately stops outreach (`action: "end"`) on negative sentiment or opt-out keywords.

---

## 📡 Official API Specification

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/healthz` | Uptime and loaded context counts |
| `GET` | `/v1/metadata` | Team info, active model, and approach summary |
| `POST` | `/v1/context` | Ingests category, merchant, customer, or trigger data with versioning |
| `POST` | `/v1/tick` | Evaluates pending triggers and returns engagement actions |
| `POST` | `/v1/reply` | Evaluates incoming merchant messages and determines next turn action |
| `POST` | `/v1/teardown`| Flushes contexts and resets state between evaluation runs |

---

## 🧪 Evaluation Results

Tested against the official `judge_simulator.py`:

```
======================================================================
                  magicpin AI Challenge — LLM Judge                   
======================================================================

[INFO] LLM Provider: Gemini (gemini-flash-latest)
[INFO] Testing LLM connection...
[PASS] LLM connected successfully

--- SCENARIO RESULTS ---
[PASS] warmup
[PASS] auto_reply
[PASS] intent
[PASS] hostile
```

---

## 🚀 Running Locally

```bash
# 1. Clone repository
git clone https://github.com/lavrastogi01/VeraForge-magicpin-bot.git
cd VeraForge-magicpin-bot

# 2. Install dependencies
pip install -r vera-bot/requirements.txt

# 3. Configure API Key in vera-bot/.env
echo "GEMINI_API_KEY=your_key_here" > vera-bot/.env

# 4. Start the server
cd vera-bot && python3 -m uvicorn main:app --host 127.0.0.1 --port 8080

# 5. Run simulator test suite
python3 judge_simulator.py
```

---

## ☁️ Deployment on Render

This repository includes [`render.yaml`](render.yaml) for instant deployment:
- **Build Command:** `pip install -r vera-bot/requirements.txt`
- **Start Command:** `cd vera-bot && uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Environment Variable:** `GEMINI_API_KEY`
