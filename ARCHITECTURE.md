# ARCHITECTURE — Phase-wise Technical Plan

Companion to PRD.md. This doc is the "how, step by step" — what gets built in each phase, what stays fixed, what changes, and the engineering details (protocols, file structure, failure handling) needed so nothing gets missed.

---

## Cross-cutting principles (apply at every phase)

- **Swap points stay isolated.** `clients/stt_client.py`, `clients/tts_client.py`, `clients/llm_client.py` are the only files touched when swapping a provider or adding a language. Telephony/orchestration code never needs to know which provider is behind each client.
- **Fail loud, fail safe.** Every external API call (Twilio, STT, TTS, LLM, order-lookup) is wrapped so a single provider hiccup degrades gracefully (a spoken "sorry, could you repeat that?") instead of a silently dead call.
- **Config validated at startup, not discovered mid-call.** Missing env vars/keys raise immediately on boot.
- **Structured logging from day one**, even if it just goes to stdout in Phase 1 — this is what Phase 4's observability builds on; retrofitting logging later is more expensive than starting with it.

---

## Phase 1 — Core Voice Loop (in progress)

**Goal:** prove a real inbound phone call can hold a natural, low-latency, multi-turn spoken conversation that actually sounds like talking to a person, not a bot. English only. One call at a time. Local machine + ngrok. Every call is recorded (audio + transcript) and opens with a recording disclosure. Zero cost: Twilio trial, Deepgram free credit, Groq free tier, ngrok free tier — no paid LLM.

**Persona design (`llm_client.py`):** the system prompt is written deliberately, not left as a generic assistant prompt. It should instruct the LLM to: keep responses short and conversational (one thought per turn, never a paragraph — nobody talks in bullet points), use natural acknowledgments ("I see", "got it", "sure, one sec"), avoid robotic/formal phrasing, and match a warm, patient tone appropriate for someone calling with a problem. This persona is the foundation Phase 2's structured intake sits on top of.

**Call flow:**
```
Customer dials Twilio number
  → Twilio sends webhook to  GET/POST /twiml/answer
  → we return TwiML: <Connect><Stream url="wss://.../media-stream"/></Connect>
    (the greeting spoken once the stream connects opens with "this call is being recorded")
  → Twilio opens WebSocket to /media-stream
  → connected → start (save streamSid) → media frames (mulaw/8kHz/base64) stream continuously
  → our WS handler forwards audio to Deepgram STT
  → Deepgram returns partial + final transcripts (endpointing built in)
  → on final transcript: call_orchestrator sends history to the LLM (Groq, streamed)
  → the LLM's streamed sentences go to Deepgram Aura TTS (streamed)
  → in parallel, raw audio frames (both directions) are appended to a local call-recording file, and each transcript line is appended to a call log — both flushed to disk when the call ends
  → TTS audio chunks sent back as `media` + `mark` messages
  → mark echoed back = agent finished speaking, ready to listen again
  → stop message = call ended, tear down per-call state
```

**File structure:**
```
calling-agent/
├── .env / .env.example / .gitignore
├── requirements.txt
├── app/
│   ├── main.py                  # FastAPI app entrypoint
│   ├── config.py                # env loading, fail-fast validation
│   ├── routes/
│   │   ├── call_control.py      # GET/POST /twiml/answer (Twilio's inbound webhook target)
│   │   └── media_stream.py      # WS /media-stream — Twilio Media Streams protocol handler
│   ├── orchestrator/
│   │   └── call_orchestrator.py # per-call state machine: STT -> LLM -> TTS -> Twilio, barge-in
│   ├── clients/
│   │   ├── stt_client.py        # Deepgram streaming STT wrapper
│   │   ├── tts_client.py        # Deepgram Aura streaming TTS wrapper
│   │   └── llm_client.py        # Groq wrapper — build_system_prompt() (persona), stream_response(history)
│   ├── audio/
│   │   └── twilio_audio.py      # base64 encode/decode, media/mark/clear message builders
│   └── recording/
│       └── call_recorder.py     # writes raw call audio to a local file + appends transcript log, per call
```

**Milestones:**
| # | Milestone | Proves |
|---|---|---|
| A | Inbound call answered, static `<Say>` greeting | Twilio account + number + inbound webhook wiring |
| B | `<Connect><Stream>` + WS handler echoes caller's own audio back | Media Streams protocol + audio format correctness |
| C | One scripted STT → LLM → TTS round trip | **Full pipeline validated end-to-end** |
| D | Looped into multi-turn conversation with history | Feels like a real conversation |
| E | Barge-in (interrupt handling via `clear`) | Feels human, not walkie-talkie |
| F | Recording (audio + transcript) + persona system prompt in place | Every call is reviewable and sounds human, not robotic |

**Accounts needed (all free):** Twilio (trial), Deepgram ($200 free credit), Groq (free API tier, no card required), ngrok (free tier).

---

## Phase 2 — Multilingual (Hindi + English) + Structured Intake + Mock Tool-Use + Outbound Trigger

**Goal:** the agent (a) understands and speaks Hindi or English, (b) runs a structured complaint intake instead of freeform chat, (c) can call a mock order-lookup tool, (d) can be triggered by a web form to call a customer back — all still free-tier, still single call at a time.

### 2.1 Language handling — design decision flagged

Two ways to support Hindi + English, with a real complexity/reliability tradeoff:

- **(Recommended) Upfront language selection.** At call start, ask once — "Press 1 or say 'English'; दबाएं 2 या बोलें 'हिंदी'" — then lock STT/TTS to that language for the rest of the call. Simple, reliable, low-risk; this is what most production systems handling multiple languages actually do.
- **Continuous per-utterance auto-detection.** Detect language on every utterance and switch STT/TTS dynamically, allowing mid-call code-switching (e.g. "Hinglish"). More seamless if it works, but meaningfully harder to get reliable — language-ID on short utterances is error-prone, and switching TTS voice mid-conversation can sound jarring if misdetected.

I'm defaulting the plan to **upfront selection** for Phase 2 (ship something reliable first), with continuous detection as a Phase 3+ stretch goal once the simpler version is proven. Flag it if you'd rather attempt continuous detection from the start — it's a real fork in `stt_client.py`'s design, better to decide before writing it than mid-build.

### 2.2 STT/TTS provider re-evaluation

Deepgram (Phase 1's choice) needs a real check for Hindi quality before we commit it to Phase 2 — not assumed. Candidates to evaluate: Deepgram (check current Hindi model quality), Google Cloud Speech-to-Text, Azure Speech, Sarvam AI (India-focused, built specifically for Hindi/Indic languages — worth a close look given this exact use case). This is a short research/spike task at the start of Phase 2, not a guess baked into code.

### 2.3 Structured intake — slot-filling state machine

Instead of "let the LLM decide what to ask," Phase 2 introduces an explicit intake schema the orchestrator tracks per call:

```
required_slots = {
  order_id: None,
  issue_category: None,   # lost | broken | wrong_item | scam | other
  description: None,
  desired_outcome: None,
}
```
Each turn: orchestrator checks which slots are still empty, and instructs the LLM (via system prompt / structured turn context) to naturally ask for the next missing one — not a rigid script, but a guaranteed checklist underneath a natural conversation. Once all slots are filled, the agent reads back a summary for confirmation before proceeding to lookup/resolution. This state machine lives in a new `app/domain/intake_schema.py`, kept separate from `llm_client.py` so the checklist can be edited without touching the LLM integration itself.

### 2.4 Order-lookup tool (mocked)

A new `app/clients/order_tool.py` exposes a `lookup_order(order_id_or_phone)` function registered as an LLM tool (Groq's OpenAI-compatible function-calling). Phase 2 backs it with a small local fake dataset (JSON/dict of sample orders) so the agent can demonstrate "I see your order #1234 shows out for delivery" — Phase 3 swaps the internals for a real API call, same function signature.

### 2.5 Outbound callback trigger

New `app/routes/complaint_intake.py`: `POST /complaint/callback` accepts `{name, phone, issue_summary}` from a web form, validates it, and uses the Twilio REST API to originate a call to `phone` — reusing the exact same `call_orchestrator`/TwiML/media-stream path as inbound calls, just pre-seeding the intake state with `issue_summary` so the agent opens with something like "Hi, I understand you had an issue with a wrong item — can you tell me more?" instead of a blank greeting.

*(Note: retry-on-no-answer, idempotency/dedupe, and endpoint authentication are Phase 3 hardening — Phase 2 just proves the trigger mechanism works for a happy-path call.)*

**File structure additions over Phase 1:**
```
app/
├── domain/
│   └── intake_schema.py      # structured checklist state machine
├── clients/
│   └── order_tool.py         # mock order-lookup, LLM tool-use
└── routes/
    └── complaint_intake.py   # POST /complaint/callback — web form trigger
```

---

## Phase 3 — Real Data Integration + Production Call Flow

**Goal:** move from "convincing demo" to "actually production-ready for one business."

- **Real order data:** `order_tool.py`'s internals point at a real or realistic sandbox order/shipment/ticketing API instead of mock data. Function signature unchanged from Phase 2 — this is the payoff of keeping it isolated.
- **Real published number:** move off the Twilio trial restriction; inbound becomes the primary path a real customer uses.
- **Outbound trigger hardening:**
  - *Idempotency:* a `complaints` store (even a simple DB table) with a dedupe key so the same form submission can't trigger two calls.
  - *Retry policy:* if the call goes unanswered/busy/voicemail, retry N times over a defined window, then mark as failed for human follow-up — never silently drop a complaint.
  - *Authentication:* the `/complaint/callback` endpoint requires a shared secret/API key or HMAC signature so only the legitimate form can trigger a call, not anyone who finds the URL.
- **Human handoff:** for issues the agent can't resolve, use Twilio's `<Dial>` to transfer/conference into a human support queue — *scope to confirm with you (PRD §14, open question 2)*.
- **Consent/compliance:** if calls are recorded (useful for quality/dispute resolution), the call should open with a disclosure ("this call may be recorded") — a compliance norm in most jurisdictions and worth building in now rather than retrofitting later.

---

## Phase 4 — Multi-Tenant Production Hardening & Scale

**Goal:** this becomes a real SaaS product serving multiple businesses at once, reliably, at volume.

- **Stateless app + shared state:** per-call state moves from an in-memory Python dict to Redis (keyed by `stream_sid`/`call_sid`), so any app server instance can pick up any call's next event — required once there's more than one server process.
- **Multi-tenant config:** a tenant table (business → Twilio number(s), knowledge base/intake schema variant, order-API credentials, language set) so `call_orchestrator` loads the right configuration per incoming call instead of one hardcoded setup.
- **Real hosting:** deploy off the laptop entirely — containerized FastAPI app, autoscaled behind a load balancer, stable public URL (no more ngrok).
- **Observability:** structured logs, per-stage latency metrics (STT/LLM/TTS), call success/failure rates, alerting on error spikes — built on the logging groundwork from Phase 1.
- **Security & compliance:** encrypt PII at rest and in transit, access-controlled admin tooling, secrets in a real secrets manager (not `.env` files), audit trail per NFR8, and a look at India's DPDP Act requirements given the customer data involved (PRD §14, open question 4).
- **Cost governance:** per-tenant usage tracking and rate limiting so one business's call volume can't blow through shared API budgets unnoticed.

---

## What stays constant across all four phases

`call_orchestrator.py`'s core loop (listen → transcribe → think → speak → repeat) and the `clients/` interface boundaries never change shape — only their internals grow (mock → real data, single language → multilingual, in-memory → Redis-backed state, single tenant → multi-tenant config). This is the direct payoff of the modular-pipeline decision made at the very start of Phase 1.
