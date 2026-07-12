# PRD — AI Calling Agent

**Author:** Shikha Upadhyay
**Status:** Draft v1
**Last updated:** 2026-07-12

---

## 1. Overview

An AI-powered voice agent that places a real phone call to a user and holds a natural, real-time spoken conversation — similar to ChatGPT's voice mode, but delivered over an actual phone line rather than an app. Phase 1 validates the core "call and talk" experience. Later phases add domain-specific knowledge and embed the same agent into a website/product use case.

## 2. Problem / Motivation

Most conversational AI today lives inside chat apps or requires the user to open a specific app/browser tab. A phone call is a lower-friction, more universal interface — no app install, no login, works on any phone. This project proves out whether a fully AI-driven phone conversation (speech in, speech out, real-time) can feel natural enough to be usable, before investing in domain-specific training and product integration.

## 3. Goals

**Phase 1 (this PRD's scope):**
- G1: System places an outbound call to a specified phone number.
- G2: The agent speaks a greeting and can hold a short back-and-forth spoken conversation.
- G3: The user's speech is transcribed accurately enough for the agent to respond sensibly.
- G4: The agent's spoken responses sound natural and arrive with low enough latency to feel like a real conversation, not a walkie-talkie exchange.
- G5: Architecture keeps the "reasoning/LLM" component isolated so it can be extended without reworking the telephony layer.

**Future / out-of-scope for Phase 1 (Phase 2+):**
- Domain-specific knowledge injection (RAG over company/product data).
- Embedding the agent into a website (text or voice widget).
- Handling inbound calls (customers calling in) rather than only outbound.
- Multi-call concurrency, call recording/analytics, CRM integration.

## 4. Non-Goals (Phase 1)

- Not building a production-scale, multi-tenant calling system.
- Not optimizing for cost at scale — this is a low-volume prototype.
- Not handling languages other than English (unless trivially supported by chosen providers).
- Not building persistent storage/database for call history.

## 5. Users & Stakeholders

- **Primary user (Phase 1):** Shikha herself — the callee and the one validating the experience.
- **Future user (Phase 2+):** End customers of whatever business use case the website integration serves (TBD).
- **Owner/builder:** Shikha, final-year BTech AI student, building this as a personal/portfolio project with a path to a real product use case.

## 6. User Stories

1. *As the user*, I can trigger a call to my phone with one action (e.g., an API call) and my phone rings.
2. *As the user*, when I answer, I hear a natural-sounding spoken greeting from the agent (not a robotic IVR voice).
3. *As the user*, I can speak normally and the agent understands what I said.
4. *As the user*, the agent replies in a relevant, coherent way, spoken back to me in a natural voice.
5. *As the user*, I can have more than one exchange in a single call (multi-turn), not just one question and one answer.
6. *As the developer*, I can later swap in domain-specific knowledge without rewriting the call-handling or audio code.

## 7. Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR1 | System can originate an outbound phone call to a configured number | Must |
| FR2 | On answer, agent plays a spoken greeting | Must |
| FR3 | System captures the caller's live speech during the call | Must |
| FR4 | Speech is converted to text in real time | Must |
| FR5 | Transcribed text is sent to an LLM to generate a response | Must |
| FR6 | LLM response is converted back to speech and played into the call | Must |
| FR7 | Conversation can continue for multiple turns within one call | Should |
| FR8 | System maintains conversation context/history within a single call | Should |
| FR9 | Agent detects when the user starts speaking while it is still talking and yields (barge-in) | Could (stretch for Phase 1) |
| FR10 | LLM prompt/knowledge layer is isolated in its own module for future domain customization | Must |

## 8. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR1 | End-to-end response latency (user stops speaking → agent starts responding) should feel conversational — target under ~2 seconds for Phase 1 |
| NFR2 | Voice output should sound natural, not robotic/synthetic-sounding |
| NFR3 | System should run reliably for a single test call at a time (no concurrency requirement yet) |
| NFR4 | All API keys/secrets kept out of source control | 
| NFR5 | Codebase modular enough that swapping any one component (STT, TTS, or LLM provider) touches only one file |

## 9. System Architecture (high-level)

```
Phone (user) <--- voice call ---> Twilio
                                     |
                                     v
                        FastAPI backend (Python)
             ┌───────────────┬───────────────┬───────────────┐
             |  STT (speech  |  LLM (Claude  |  TTS (text to |
             |  to text)     |  API) — brain |  speech)      |
             └───────────────┴───────────────┴───────────────┘
```

- **Telephony:** Twilio — places the outbound call and streams call audio to/from our backend over a WebSocket.
- **Speech-to-Text:** Deepgram streaming API — converts caller speech to text in real time.
- **LLM:** Anthropic Claude API — generates the agent's response; isolated in its own module so Phase 2 can add retrieval/domain knowledge here without touching telephony code.
- **Text-to-Speech:** Deepgram Aura (swappable for ElevenLabs later for higher voice quality) — converts the response back to natural-sounding audio.
- **Backend:** Python/FastAPI, run locally during prototyping, exposed to Twilio via an ngrok tunnel.

Full technical design (protocol details, file structure, build order) is in the accompanying technical plan.

## 10. External Dependencies

| Service | Purpose | Notes |
|---|---|---|
| Twilio | Outbound calling + real-time audio streaming | Trial account sufficient (calls to verified numbers only) |
| Deepgram | Speech-to-text + text-to-speech | $200 free credit |
| Anthropic (Claude API) | Conversational reasoning/response generation | Requires small prepaid balance |
| ngrok | Exposes local dev server to Twilio over a public URL | Free tier sufficient |

## 11. Success Metrics / Acceptance Criteria

Phase 1 is considered successful when:
- [ ] A real phone call is placed to the user's number and answered.
- [ ] The user hears a spoken greeting that sounds natural.
- [ ] The user speaks a sentence and the agent's spoken reply is relevant to what was said.
- [ ] At least 2–3 conversational turns happen in a single call without the system breaking.
- [ ] The LLM/reasoning component is verified to be swappable in isolation (code review check, not a runtime test).

## 12. Milestones

| Milestone | Description | Outcome |
|---|---|---|
| M1 | Outbound call + static scripted greeting | Confirms telephony wiring works |
| M2 | Live audio loopback over the call | Confirms real-time audio streaming works both directions |
| M3 | One full STT → LLM → TTS round trip | **Core concept validated** — the agent hears, thinks, and speaks |
| M4 | Multi-turn conversation with memory | Feels like a real back-and-forth conversation |
| M5 | Barge-in / interruption handling | Feels like talking to a human, not taking turns with a walkie-talkie |

## 13. Risks & Assumptions

| Risk | Mitigation |
|---|---|
| Real-time latency across STT → LLM → TTS may feel sluggish | Use streaming APIs at each stage; start responding before the full LLM output is ready |
| Trial-tier accounts (Twilio) restrict calling to verified numbers | Acceptable for Phase 1 since the only callee is the user herself |
| API costs if left running / scaled carelessly | Low call volume expected during prototyping; revisit before any public-facing use |
| Voice may sound unnatural depending on TTS provider | Start with Deepgram Aura; swap to ElevenLabs (already planned as a one-file change) if quality isn't good enough |

## 14. Future Roadmap (Phase 2+)

- Inject domain-specific knowledge (product/company info) via RAG into the LLM module.
- Reuse the same LLM module behind a website chat/voice widget.
- Consider inbound call handling if the use case requires customers to call in.
- Add persistence (call transcripts, analytics) if this moves beyond prototype.
