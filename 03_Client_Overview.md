# PP Message Center Auto-Analysis — Business Overview

**Audience:** Business stakeholders, solution owners, line-of-business leaders, anyone deciding whether to adopt this in their organisation.
**Date:** June 2026
**Owner:** Sunneteam

---

## The Problem in One Sentence

Microsoft 365 Message Center publishes roughly **86,000 announcements** across the tenant lifetime. The handful that break your Power Platform flows are buried in that noise — and you usually find out when a flow stops working.

---

## What This Solution Delivers

A fully automated pipeline that reads every Power Platform-related announcement, classifies it, stores it in a searchable repository, and emails the right people **only when action is required**.

### Outcomes you can expect

| Outcome | Before | After |
|---|---|---|
| Time to notice a breaking change | Days or weeks (or never) | Same business day |
| Manual review effort | One person, several hours a week | Zero for routine items; minutes for flagged items |
| Knowledge repository | Spread across emails and tickets | Single SharePoint list, structured, searchable |
| Cost | Hidden — incidents from missed announcements | ~$0.30 per announcement processed in AI cost |
| Lock-in | None — runs on your existing Power Platform |

---

## How It Works (No Technical Detail)

1. A new Microsoft announcement lands.
2. The system reads it, identifies whether it's a maintenance notice, a new feature, a breaking change, or something unclear.
3. It writes the verdict to a structured list — title, category, priority, impact, summary, recommended actions.
4. If action is required, an email goes to the administrator group. If it's routine, the system files it and moves on. You are not pinged for noise.

The intelligence comes from a Microsoft AI model (GPT-5 reasoning, via AI Builder) running inside your own tenant. No data leaves the Microsoft 365 boundary.

---

## Why We Built It Instead of Buying

We looked at three alternatives:

| Option | Why it didn't fit |
|---|---|
| Native M365 Admin Portal + email digests | No filtering by Power Platform, no AI triage, fully manual |
| Third-party governance tools (CoreView, AdminDroid, ENow) | $40–$60k/yr licenses; generic tenant-wide, not Power Platform-specific; no AI classification |
| Custom Microsoft Graph scripts | Code-first; sits outside low-code governance; high build and maintenance cost |
| **This solution** | Low-code, Power Platform-native, AI-driven, ~$0.30 per run, owned by your team |

---

## What's In Scope vs. Out of Scope

**In scope:**
- Power Platform announcements (Power Apps, Power Automate, Dataverse, Copilot for Power Platform)
- Classification: category, priority, impact level
- AI-generated summary in English (1–2 sentences)
- Repository entries and email notifications
- Deduplication so the same announcement is never processed twice

**Out of scope:**
- Auto-remediation — the system tells you something is happening; deciding what to do is on the administrator
- Announcements unrelated to Power Platform (Teams, Exchange, etc.) — not classified, ignored at the source filter
- Non-Microsoft services

---

## Cost and Effort

**To stand up:**
- One Power Platform administrator, half a day, following the admin guide
- One AI Builder prompt configured and tested
- Two SharePoint lists (or one site with both lists)
- A service account and a distribution list for alerts

**To run:**
- ~30 AI Builder credits per announcement processed
- ~6.7 seconds per announcement
- Zero human time for routine items
- For backfilling the 86k historical records: budget approximately 2.5 million AI credits one-time, or filter to recent months only

**To maintain:**
- The system prompt is the only volatile piece — expect to tune it once or twice per quarter as MC announcement formats evolve
- Periodic spot-check of `Category = Other` items (these are flagged automatically for human review)

---

## Results from Pilot

During the WRO-BOOST 2026 build:

- **100%** of test scenarios passed (Maintenance, New Feature, Breaking Change, Unclear, Duplicate, Invalid JSON)
- **6.7 s** average AI runtime
- **0** unhandled errors across the full regression suite
- Two AI approaches built and compared (single-shot Prompt vs. multi-step Agent) — Prompt selected for production on cost and predictability, Agent kept documented as the upgrade path for organisations that need deeper analysis

---

## What You Need to Decide

1. **Email distribution list** — who receives the "action required" alerts? (Default: Power Platform administrators DL)
2. **Backfill strategy** — process the full 86k history, the last 12 months only, or only new items from go-live? Budget impact differs by an order of magnitude.
3. **Escalation path** — when a `Breaking Change` lands, who acts? Is the workflow ticket → human review → remediation, or something else?
4. **Adoption of the upgrade path** — for organisations that need richer multi-step analysis (executive + technical summary, deeper reasoning), the Copilot Studio Agent variant is ready to deploy. Decide whether to keep it in reserve or activate.

---

## Next Steps After Go-Live

These are scoped but not delivered in v1 — natural extensions if value is proven:

- **Microsoft Teams alerts** — alongside email, post into a Teams channel for higher visibility
- **Power BI dashboard** — leadership view: breaking changes by month, average time to acknowledge, categories trending
- **Agent upgrade** — multi-step analysis with executive + technical summaries
- **Translation pass** — for tenants where MC items occasionally arrive in non-English

---

## Contact

For commercial questions, scoping, or rollout planning: Sunneteam, via the WRO-BOOST channel.
For technical questions: see the Administrator Guide and Technical Documentation.
