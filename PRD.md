# Spec: PRD — Hercules agent Core

**Version:** 1.0
**Status:** Approved
**Author:** Hercules agent Agent
**Date:** 2026-03-06
**Reviewers:** Sandeco

---

## 1. Summary

SandeClaw is a personal Artificial Intelligence agent designed to operate 100% locally on the user's desktop. It receives commands exclusively via Telegram, processes them through a pipeline that supports multiple dynamic LLMs, and has persistent access to memory in SQLite.

---

## 2. Context and Motivation

**Problem:**
Agents hosted in the cloud and third-party services require exposing private data or have high recurring costs, besides the lack of total governance over custom "skills". The user does not have full control over instances like OpenClaw without encountering cloud complexity or vendor lock-in.

**Evidence:**
Previous attempts based on OpenClaw worked, but the primary intention now is to maintain a minimalist base under total user control, operating on the user's own OS.

**Why now:**
The rise of super-efficient LLMs (Gemini 1.5/2.0+ and DeepSeek) combined with the ease of the Telegram API allows running a personal agent without the operational frictions of web UI.

---

## 3. Goals (Objectives)

- [ ] G-01: Primarily operate by receiving and responding to requests via Telegram using `grammy`.
- [ ] G-02: Interchange "brains" (LLMs) using standardization (DeepSeek, Gemini).
- [ ] G-03: Retain context across multiple turns with SQLite via TS repositories.
- [ ] G-04: Respect strict authorization limits via user ID (whitelist).

**Success metrics:**
| Metric | Current Baseline | Target | Deadline |
|--------|------------------|--------|----------|
| Local bot API uptime | 0% | 99% after tests | 30 days |
| Dynamic Skill hot-reload | Not supported | 1 second reload | 10 days |

---

## 4. Non-Goals (Out of Scope)

- NG-01: Will not have a Web interface (React/Vue/HTML). The interface is exclusively Telegram.
- NG-02: Will not support multiple users beyond the strict Whitelist. Not SaaS.
- NG-03: Support for robust databases like PostgreSQL/Mongo. Exclusive focus on minimal local SQLite.

---

## 5. Users and Personas

**Primary User:** Sandeco (owner), accessing via mobile device or desktop via Telegram client, using IDs in restricted whitelist.

**Current Journey (without feature):**
The user must manually manage APIs or log into multiple web tabs (ChatGPT, Gemini) to trigger "skills" in independent text blocks without local file system integrations.

**Future Journey (with feature):**
The user sends a chat on Telegram, Hercules agent runs locally in background in a terminal, calls LLMs, reads Skills from local folders, triggers tools, and responds in the same chat organically.

---

## 6. Functional Requirements

### 6.1 Main Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| RF-01 | The system must run via persistent polling loop of the Grammy library | Must | The terminal triggers the listener with `npm run dev` and intercepts messages without closing. |
| RF-02 | The system must validate all incoming messages against the `TELEGRAM_ALLOWED_USER_IDS` variable | Must | An unregistered user receives instant ignore; no sensitive log is triggered and no API key is wasted. |
| RF-03 | The system must alternate "LLMs" by instantiating factories (`ProviderFactory`) | Must | Changing "gemini" to "deepseek" in config sends prompts directly to the target endpoint correctly parsed. |

### 6.2 Main Flow (Happy Path)

1. The user sends a string "summarize for me" on Telegram.
2. The PC bot system intercepts (via Facade of `AgentController`).
3. The system checks if ID belongs to Whitelist (YES).
4. The system sends to Loop (ReAct / AgentLoop) with Local Context saved from SQLite database.
5. The selected LLM processes, finds or not the necessary Tool.
6. The response returns via Output Handler in the Telegram chat.

### 6.3 Alternative Flows

**Alternative Flow A — LLM API Failure:**
1. Primary LLM (ex: gemini) overloaded (503).
2. The AgentLoop attempts fallback to another config or fails gracefully by sending warning to Telegram instead of breaking the Promise of the main engine.

---

## 7. Non-Functional Requirements

| ID | Requirement | Target Value | Observation |
|----|-------------|--------------|-------------|
| RNF-01 | Message relay latency | < 1000ms | Do not confuse bot delay with LLM provider API delay. |
| RNF-02 | Agile Persistence | SQLite Synchronous | `better-sqlite3` chosen for performance and simplicity in single-thread Node.js |

---

## 8. Design and Interface

**Affected Components:** Terminal log-output, and Chats of the Telegram application of Whitelisted user.

**UI States (In Telegram):**
- Processing state: The bot signals typing action via Telegram Chat Action until the actual send request is executed.

---

## 9. Data Model

**Entities modified/persisted in `./data/`**
```sql
conversations {
  id: string        // UUID or unique Hash of the user thread
  user_id: string   // The whitelisted originator
  provider: string  // ex: 'gemini'
}
messages {
  conversation_id: string
  role: string      // 'user'|'assistant'|'system'
  content: string   // Raw Payload of the conversation
}
```

---

## 10. Integrations and Dependencies

| Dependency | Type | Impact if unavailable |
|------------|------|----------------------|
| Telegram API | Mandatory | The agent becomes unusable / Node sleep mode. |
| APIs (Gemini/DeepSeek) | Mandatory | No logical reasoning. Will need to attempt fallback in `ProviderFactory`. |
| `Grammy` package | Mandatory | Node core library of the polling architecture |

---

## 11. Edge Cases and Error Treatment

| Scenario | Trigger | Expected Behavior |
|----------|---------|-------------------|
| EC-01: Injection by Fake User | Receiving requests from bots/crawlers | Cut at Top-Level Middleware without reaching DB. |
| EC-02: Database blocked | Two simultaneous loops attempt intense writing | Wait via natural timeout of WAL driver (Write Ahead Logic), otherwise discard soft and notify LLM. |
| EC-03: Invalid Key | The `.env` file is corrupted or API key discontinued | Agent attempts to start, logs fatal auth error in Terminal and notifies in log that provider `X` failed. |
| EC-04: Excessive CPU processing | Huge files sent for local summary/pdf | Throttle by threshold and say "This file exceeds locally supported limits." |

---

## 12. Security and Privacy

- **Authentication:** Based exclusively on Telegram User ID provided in the `.env` array (`TELEGRAM_ALLOWED_USER_IDS`).
- **Authorization:** That userId = Admin, others = rejected.

---

## 13. Rollout Plan

- **Strategy:** Deploy on local machine running `npm run dev` for the primary instance.
- **Monitoring:** Log to Stdout in terminal to track Agent Loop transitions and Request failures.

---

## 14. Open Questions
