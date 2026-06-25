# Project Workflow Summary — PP Message Center Auto-Analysis

**Project:** Auto-Analysis of Message Center Announcements for Power Platform
**Team:** Sunneteam (Politechnika Wrocławska × Volvo, WRO-BOOST Teams Projects 2026)
**Timeline:** 12 March 2026 – 14 June 2026 (5 sprints)

---

## Team and Responsibilities

| Member | Role | Responsibility |
|---|---|---|
| Yehor Sakovtsev (YS) | Project Manager / Team Lead | Planning, coordination, sprint delivery, Power Automate workflow corrections |
| Dmytro Zavhorodnii (DZ) | Business Analyst | Requirements, scope, AI classification module (Gemma3), error-handling implementation |
| Yauheniya Drozd (YD) | IT Architect | Solution design, dictionary of terms, classification criteria |
| Yahor Andreichykau (YA) | Test Manager / Tester | Verification and acceptance, integration testing, reports for the client |
| All members | Developers | Flow build, AI prompt build, agent configuration |

The same four people rotated through six functional roles described in the final report (PM, BA, IT Architect, Developer, Test Manager) — roles were responsibilities, not headcount.

---

## Sprint Timeline

The project ran in five two-week sprints. The work moved from analysis → architecture → implementation → AI integration → stabilisation and documentation.

### Sprint 1 — Initial Phase Wrap-Up (12 Mar – 26 Mar 2026)

**Goal:** Close the discovery phase — Use Case documentation, schedule update, technical-tool configuration before the Volvo meeting.

**Highlights:**
- Backlog grew from 4 to 21 tasks in a single day (full decomposition for the planning phase)
- Project description and Use Case diagram delivered — foundation for development
- Cumulative-flow chart shows a smooth, predictable cadence (4–5 items in progress at once); no anomalies
- Green-area jump on 26–27 March = several documentation items accepted

**What got done:** discovery artifacts (project description, Use Case diagram), schedule update, Jira/Power Platform tooling set up for the team.

---

### Sprint 2 — From Planning to Build (01 Apr – 07 May 2026)

**Goal:** Implement core AI-agent logic and integrate the database with the workflow — foundation for automatic announcement analysis.

**Jira process change:** new statuses introduced — "Do omówienia" (To discuss), "Do weryfikacji" (To verify), "Oczekiwanie na feedback" (Awaiting feedback). When an item enters "Do weryfikacji" three questions are auto-attached: Does the solution work? Is the documentation ready? Were the tests done?

**Highlights:**
- All 7 planned items closed (some overdue — waiting on company feedback)
- **DZ delivered the classification module (AAMCAFPP-28)** — native on Gemma3 LLM with a classification-specific layer; throughput 5–10 messages per 3 minutes; pre-labeled DB acceleration mechanism added
- Power Platforms Admin Center configured; database wired to workflow + agent (AAMCAFPP-25, AAMCAFPP-27)
- First Power BI report draft + sample test workflows (AAMCAFPP-23, AAMCAFPP-24)
- Previous-sprint report finalised (AAMCAFPP-22)

**Who did what:** DZ — classification module; YS/YD — admin centre + DB integration; YA — workflow testing; reports rotated.

---

### Sprint 3 — (No report available)

No report was attached for Sprint 3. Based on the project plan (the Sprint 4 report references its results), this sprint sat between development and AI-agent rollout — most likely covering the first end-to-end integration tests and the prep work for Copilot Studio integration.

---

### Sprint 4 — Application Layer + AI Agent (29 May – 05 Jun 2026)

**Goal:** Finalise the Power Automate business logic and stand up the AI-agent in Microsoft Copilot Studio.

**Highlights:**
- All 5 planned items closed as **GOTOWE**. Some slipped past 31 May / 2 Jun deadlines — root cause: prompt tuning for non-standard message structure and the Copilot Studio integration **without HTTP connectors** (a hard constraint from the corporate environment)
- YA, DZ, YD, YS worked in parallel — Power Automate logic on one track, conversational-bot configuration on the other
- Items closed continuously end-of-May into first-week-of-June

**Delivered:**
- **Workflow finalised** (AAMCAFPP-34, AAMCAFPP-18): Power Automate flows for distributing announcements
- **AI-agent stood up in Copilot Studio** (AAMCAFPP-36)
- **Dedicated system prompt designed and deployed** (AAMCAFPP-39)
- **Stakeholder feedback round processed** (AAMCAFPP-33)

---

### Sprint 5 — Stabilisation + Documentation (05 Jun – 12 Jun 2026)

**Goal:** Reach system stability through full integration testing (including AI validation and the no-HTTP mechanism) and deliver the complete technical documentation plus admin guide.

**Highlights:**
- All 3 key technical-test items closed — solution stable
- Documentation items in advanced "in-progress" state (intentional — to incorporate the late integration-test findings)
- The no-HTTP data-retrieval test confirmed the alternative integration mechanism is fully stable inside the Power Platform tenant
- YA + DZ ran the heavy integration tests, fed corrections to YS for workflow updates immediately
- Critical errors and failure-handling closed before sprint end

**Delivered:**
- **End-to-end tests + stabilisation** (AAMCAFPP-19, AAMCAFPP-40): full integration test of MC pull without the blocked HTTP protocol
- **Error resilience and patches** (AAMCAFPP-41, AAMCAFPP-38): YS implemented advanced error handling in Power Automate, protecting the system against repository unavailability
- **Documentation work in progress** (AAMCAFPP-20, AAMCAFPP-42, AAMCAFPP-43, AAMCAFPP-44): templates and structure for the architecture doc (-42) and admin guide (-43) prepared

| Item | Title | Status | Owner |
|---|---|---|---|
| AAMCAFPP-35 | Build report for company | Done | YA |
| AAMCAFPP-38 | Implement workflow patches | Done | YS |
| AAMCAFPP-41 | Error-handling implementation | In progress | DZ |
| AAMCAFPP-19 | System testing and bug-fixing | To verify | YS |
| AAMCAFPP-40 | Integration tests for HTTP-free data retrieval | To verify | YA |
| AAMCAFPP-20 | Technical documentation prep | To discuss | DZ |
| AAMCAFPP-42 | Architecture documentation prep | To discuss | YS |
| AAMCAFPP-43 | Admin guide prep | To discuss | YA |
| AAMCAFPP-44 | Glossary + classification criteria | To discuss | YD |

---

## End-to-End Workflow (cross-sprint view)

1. **Discovery & scope** (Sprint 1) — Use Case, requirements, environment setup.
2. **Core build** (Sprint 2) — classification module (Gemma3), DB-workflow integration, Power BI scaffolding, sample test workflows. Jira process refined with verification statuses.
3. **Integration & agent** (Sprints 3–4) — Power Automate finalisation, Copilot Studio agent with no-HTTP connectors, system prompt design, stakeholder feedback loop.
4. **Stabilisation & documentation** (Sprint 5) — integration tests against 86k records, advanced error handling, repository-unavailability protection, technical doc + admin guide + architecture doc + glossary.

**Engineering practices throughout:**
- ALM split DEV → TEST → PROD from sprint 2 onward
- All flow stages built as named **Scopes** (9 total) — independent testability and a global Try/Catch
- Environment variables instead of hard-coded credentials
- Two competing AI approaches built and benchmarked (Prompt vs. Agent) — Prompt selected for production on cost/determinism; Agent kept documented as the upgrade path
