# PRD — Domain-Specific Multilingual AI Calling Agent for Customer Support

**Author:** Shikha Upadhyay
**Status:** Draft v2 (revised after product vision clarified)
**Last updated:** 2026-07-12

---

## 1. Overview

A phone-based AI support agent that businesses (starting with e-commerce/logistics) can embed as their customer support line. A customer with a problem — a lost, broken, wrong, or scam parcel — can either **call in directly**, or **submit a short complaint form and have the agent call them back**. Either way, the agent speaks in the customer's preferred language (starting with Hindi or English), runs through a structured intake so nothing important is missed, and can look up real order/shipment data to help resolve the issue. This is being built as a **sellable product** (B2B: businesses adopt it as their support channel), not only a personal prototype — every design decision should hold up as production infrastructure, not a demo.

Phase 1 (in progress) validates the core technical capability — a real-time phone conversation that sounds and feels natural — before layering on language breadth, structured domain intake, real data integration, and production/multi-tenant hardening.

## 2. Problem & Motivation

Text-based chat assistants are now standard on e-commerce/logistics websites, but they carry a hidden assumption: the customer can read/type, usually in English. A customer whose parcel arrived broken, wrong, or was possibly scammed — and who isn't comfortable typing a complaint in English — is left with no good channel. Voice is the natural interface people already use to complain or ask for help; a phone call in one's own language removes both the literacy and language barriers a chat widget imposes.

This is the gap the product targets: **a support phone channel, not a chat widget**, that understands and speaks back in the customer's language, reliably collects what it needs to act, and can act on real order data — not just talk.

## 3. Business Model & Users

- **Business (tenant):** an e-commerce/logistics company that adopts this as (part of) their customer support line.
- **End customer:** someone with a parcel-related issue, who may prefer Hindi over English and may not want to (or be able to) use a text chat interface, or may prefer to just submit a quick form and be called back.
- **Shikha:** building and intending to sell this as a product to businesses in this space.

This B2B framing matters for later phases: eventually the system needs to support multiple businesses, each with their own phone number, knowledge base, and order-system connection — not just one hardcoded configuration.

## 4. Two Conversation Entry Points

1. **Inbound:** the customer calls a published support number directly. The agent answers and runs the same structured intake/resolution flow described below.
2. **Outbound (triggered callback):** the customer submits a short web form (name, phone number, one-line issue) on the business's site. This triggers the agent to call them back and run the same structured intake/resolution flow. *(Chosen as the first, simplest trigger — richer intake channels like chatbot handoff or existing ticketing systems are a later possibility, not required now.)*

Both entry points converge on the same conversational core (`call_orchestrator.py` + `llm_client.py`) — the only difference is how the call starts (Twilio answering an inbound call vs. our backend originating one via the Twilio REST API after a form submission). This is exactly why Phase 1's outbound-calling code isn't wasted: it's the real mechanism for entry point 2, not a throwaway test harness.

## 5. Structured Intake (not freeform chat)

Per your explicit direction, the agent follows a **defined checklist** during every complaint conversation rather than letting the LLM freely decide what to ask — this guarantees consistent, reliable data capture across every call, which matters a lot for a product being sold to businesses. Baseline checklist (to refine once we're deeper in Phase 2):

- Order/tracking ID (look up via the order tool if the customer doesn't have it handy — e.g. by phone number or name)
- Issue category: lost / broken / wrong item / suspected scam / other
- Description of the issue in the customer's own words
- Desired outcome (replacement, refund, investigation, just wants to know status)
- Confirmation: agent reads back what it understood before proceeding, so the customer can correct it

The agent should attempt to resolve the issue on the same call where possible (e.g., pulling up order status), and clearly log/escalate what it can't resolve — not just collect information passively.

## 6. Goals by Phase

**Phase 1 — Prove the core voice loop (current phase, in progress)**
- A real inbound phone call is answered by the agent and a natural, low-latency, multi-turn spoken conversation happens.
- English only for now; Hindi is deferred to Phase 2 so the STT/TTS/LLM plumbing is proven before adding language complexity.
- Free-tier services throughout; single call at a time; local dev machine + ngrok is acceptable.
- The LLM ("brain") stays isolated in its own module so nothing here needs rework when Phase 2 adds language + domain knowledge.
- Conversation is generic/small-talk at this stage — the structured intake checklist is introduced in Phase 2, once the plumbing works.

**Phase 2 — Multilingual (Hindi + English) + structured domain intake**
- Agent detects whether the caller is speaking Hindi or English (per-utterance) and responds in the same language, in a natural-sounding voice.
- Structured complaint-intake checklist (§5) implemented, backed by domain knowledge about parcel complaint categories/policies.
- Web form → outbound callback trigger built (entry point 2), initially calling a test number (not yet a real published support line).
- Agent can call a **mocked** order-lookup tool (fake sample order/shipment data) to demonstrate acting on real data, laying groundwork for Phase 3's real integration.

**Phase 3 — Real data integration + production call flow**
- Publish a real support number as the primary inbound entry point.
- Connect the order-lookup tool to a real (or realistic sandbox) order/shipment/ticketing API.
- Add a human-handoff path for issues the AI can't resolve (assumption to confirm — see §14).
- Harden the outbound-callback trigger: retry policy for no-answer/busy/voicemail, idempotency (don't double-call for one complaint), authenticated webhook so only the legitimate form can trigger a call.

**Phase 4 — Production hardening & multi-tenant scale**
- Move off laptop/ngrok to real hosting; support multiple simultaneous calls (stateless app servers + shared state store).
- Multi-tenancy: each business gets its own number, knowledge base, and order-system credentials, isolated from others.
- Security/compliance for handling customer PII (names, addresses, order details) over voice calls; observability, monitoring, alerting; cost/rate management across providers at scale.

## 7. Non-Goals (for now)

- Supporting languages beyond Hindi + English until Phase 2 is validated with these two.
- Building multi-tenant SaaS infrastructure before the core experience (Phase 1–2) is proven to actually work well.
- Payment/refund processing — **assumption to confirm**: the agent's job is to understand, look up, and route/resolve or escalate, not to move money directly. Flagged in §14, not decided unilaterally.
- Intake channels beyond the web form (chatbot handoff, email, existing ticketing systems) until the form-triggered flow is proven.

## 8. User Stories

1. *As a customer*, I can call a support number and speak in Hindi or English about my parcel problem, and the agent understands me either way.
2. *As a customer*, I can instead submit a quick form describing my issue and get called back, instead of typing out a full complaint.
3. *As a customer*, the agent asks me clear, consistent questions (what happened, my order, what I want done) and reads back what it understood before moving on.
4. *As a customer*, if the agent needs my order details, it can look them up instead of asking me to dig up an order number myself.
5. *As a business (tenant)*, I can offer this as my support line with my own knowledge base and order data connected, without customers noticing it's not a human (unless it can't help, in which case it hands off cleanly).
6. *As the developer*, I can extend language support, the intake checklist, or the order-lookup integration without rewriting the telephony/audio layer each time.

## 9. Functional Requirements

| ID | Requirement | Phase | Priority |
|----|-------------|-------|----------|
| FR1 | System can receive/answer an inbound phone call | 1 | Must |
| FR2 | On answer, agent plays a spoken greeting | 1 | Must |
| FR3 | System captures the caller's live speech during the call | 1 | Must |
| FR4 | Speech is converted to text in real time | 1 | Must |
| FR5 | Transcribed text is sent to an LLM to generate a response | 1 | Must |
| FR6 | LLM response is converted back to speech and played into the call | 1 | Must |
| FR7 | Conversation can continue for multiple turns within one call | 1 | Should |
| FR8 | System maintains conversation context/history within a single call | 1 | Should |
| FR9 | Agent detects when the user starts speaking while it is still talking and yields (barge-in) | 1 | Could (stretch) |
| FR10 | LLM prompt/knowledge layer is isolated in its own module for future domain customization | 1 | Must |
| FR10a | Every call is recorded (audio + transcript) to a local file for review | 1 | Must |
| FR10b | Agent's persona/speaking style (natural, human-like phrasing, pacing, empathy) is explicitly designed into the system prompt, not left to default LLM behavior | 1 | Must |
| FR10c | Agent discloses "this call is being recorded" at the start of every call | 1 | Must |
| FR11 | Agent detects spoken language (Hindi vs English) per utterance | 2 | Must |
| FR12 | Agent responds in the same language it was addressed in, with a natural voice for that language | 2 | Must |
| FR13 | Agent follows a structured intake checklist (order ID, issue category, description, desired outcome, confirmation read-back) | 2 | Must |
| FR14 | Agent can invoke a tool/function to look up order/shipment data mid-conversation | 2 | Must |
| FR15 | Web form submission triggers an outbound callback to the customer | 2 | Must |
| FR16 | Order-lookup tool connects to a real business order/ticketing system | 3 | Must |
| FR17 | System supports a real, published inbound support number as the primary call path | 3 | Must |
| FR18 | Outbound callback trigger has retry policy (no-answer/busy/voicemail) and is idempotent (no duplicate calls per complaint) | 3 | Must |
| FR19 | Callback-trigger endpoint is authenticated so only the legitimate form/system can initiate a call | 3 | Must |
| FR20 | Agent can escalate/hand off to a human agent when it cannot resolve an issue | 3 | Should (confirm scope, see §14) |
| FR21 | System supports multiple businesses (tenants), each with isolated number/knowledge base/data | 4 | Must |

## 10. Non-Functional Requirements

| ID | Requirement | Relevant Phase |
|----|-------------|-----------------|
| NFR1 | End-to-end response latency (user stops speaking → agent starts responding) should feel conversational — target under ~1.5–2s | 1+ |
| NFR2 | Voice output should sound natural in both English and Hindi, not robotic/synthetic | 1–2 |
| NFR3 | System should run reliably for a single test call at a time in Phase 1; must support concurrent calls by Phase 4 | 1 → 4 |
| NFR4 | All API keys/secrets kept out of source control | 1+ |
| NFR5 | Codebase modular enough that swapping any one component (STT, TTS, LLM, or language) touches only one file/module | 1+ |
| NFR6 | Customer PII (name, address, order details, call audio/transcripts) handled securely — encrypted at rest/in transit, access-controlled | 3–4 |
| NFR7 | System must be horizontally scalable to handle many simultaneous calls across many businesses | 4 |
| NFR8 | Clear audit trail / call transcript logging for support quality and dispute resolution | 3–4 |
| NFR9 | Outbound callback flow must never call a customer twice for the same complaint, and must fail gracefully (log + surface for retry) if unreachable | 3 |

## 11. System Architecture

High-level architecture is phase-dependent (what changes vs. stays fixed at each phase). See **ARCHITECTURE.md** for the full phase-by-phase breakdown, protocol details, and component diagrams. Summary of the fixed "spine" that doesn't change across phases:

```
                 ┌── Inbound: customer dials support number
Phone (customer) ┤                                              Twilio (telephony)
                 └── Outbound: web form → backend triggers call ─────┘
                                          |
                                          v
                             FastAPI backend (Python)
             ┌────────────────┬──────────────────────┬────────────────┐
             |  STT (speech   |  LLM (Groq, free) —  |  TTS (text to  |
             |  to text,      |  brain + structured  |  speech,       |
             |  language-aware)|  intake + tools      |  language-aware)|
             └────────────────┴──────────────────────┴────────────────┘
```

- **Telephony:** Twilio — handles both inbound answering and outbound origination.
- **Speech-to-Text / Text-to-Speech:** Phase 1 uses Deepgram (English) for the simplest possible working pipeline. **Phase 2 requires evaluating providers for Hindi + English quality specifically — not yet decided (see Open Questions, §14).**
- **LLM:** Groq API (free tier, fast inference — chosen to keep the project at zero cost and to help the latency budget) — isolated in its own module (`llm_client.py`) from day one; Phase 2 adds the structured intake logic + domain knowledge + tool-use (order lookup) here without touching telephony/audio code. Hindi conversational quality on Groq's open-source models is unverified — to be tested in Phase 2 and swapped (to e.g. Gemini or Claude) if it isn't good enough. Claude remains the recommended upgrade once the product is monetized and quality/cost tradeoffs shift.
- **Backend:** Python/FastAPI; local + ngrok in Phase 1–2, real hosting from Phase 3 onward.

## 12. External Dependencies

| Service | Purpose | Status |
|---|---|---|
| Twilio | Inbound + outbound calling, real-time audio streaming | Phase 1: trial account |
| Deepgram | English speech-to-text + text-to-speech | Phase 1 default |
| *(To evaluate for Phase 2)* Hindi+English STT/TTS provider | Multilingual speech in/out | **Not yet decided** — candidates to evaluate include Deepgram (check current Hindi support quality), Google Cloud Speech, Azure Speech, and Sarvam AI (India-focused, purpose-built for Hindi/Indic languages) |
| Groq API | Conversational reasoning + structured intake + tool-use (order lookup) | In use from Phase 1 — genuinely free tier, no billing setup required |
| ngrok | Exposes local dev server to Twilio | Phase 1–2 only |
| *(Phase 3)* Order/shipment/ticketing API | Real data for order-lookup tool | Not yet identified — real or sandbox system TBD |
| *(Phase 2)* Web form / hosting for the complaint form | Triggers the outbound callback | Not yet built — simplest option (e.g. a static form posting to our backend) to be decided when we reach Phase 2 |

## 13. Success Metrics / Acceptance Criteria

**Phase 1 done when:**
- [ ] An inbound call to the Twilio number is answered by the agent.
- [ ] The caller hears a natural-sounding spoken greeting.
- [ ] The caller speaks a sentence and receives a relevant spoken reply.
- [ ] At least 2–3 conversational turns happen in a single call without breaking.
- [ ] The LLM module is confirmed swappable/extensible in isolation (code review, not runtime).

**Phase 2 done when:**
- [ ] The agent correctly detects and responds in Hindi vs. English per utterance.
- [ ] The agent runs through the full structured intake checklist and reads back a correct summary.
- [ ] Submitting the web form successfully triggers an outbound call that runs the same intake flow.
- [ ] The agent can call a mock order-lookup tool mid-conversation and use the result in its spoken response.

*(Phase 3/4 acceptance criteria to be defined once Phase 2 is complete and the real data-integration partner/system is identified.)*

## 14. Open Questions (need your input — not blocking Phase 1, but worth deciding before Phase 3)

1. **Payment/refunds:** Should the agent ever initiate a refund/replacement action, or strictly diagnose + look up + escalate/route, leaving money-moving actions to the business's existing systems? (PRD currently assumes the latter.)
2. **Human handoff (FR20):** Is transferring to a live human agent in scope at all, or is "AI resolves or the customer is told to try another channel" acceptable for the first sellable version?
3. **Phase 3 data partner:** Do you have (or plan to get) an actual business/order-system to integrate with, or should Phase 3 target a realistic sandbox/mock system to demonstrate the capability without a real partner yet?
4. **Compliance:** Any awareness of specific data-protection requirements you want designed in from the start (e.g., India's DPDP Act, call-recording consent norms — many jurisdictions require telling the caller "this call may be recorded")? Worth a light-touch look before Phase 3, not urgent for Phase 1.
5. **Web form ownership:** Should we build the complaint-intake web form ourselves as part of this project (simple hosted form), or will it live on the business's existing website and just needs to call our API? Affects whether "build a form" is one of our tasks or an integration contract we define and hand off.

## 15. Roadmap Summary

Phase 1 (now) → Phase 2 (Hindi + structured intake + web-form callback trigger + mock order lookup) → Phase 3 (real data + published number + retry/idempotency hardening + handoff) → Phase 4 (multi-tenant, scale, security hardening). Full technical detail per phase is in **ARCHITECTURE.md**.
