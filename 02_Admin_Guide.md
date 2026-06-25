# Administrator Guide — PP Message Center Auto-Analysis

**Audience:** Power Platform administrators, M365 tenant administrators, DevOps engineers responsible for governance.
**Version:** 1.0 — June 2026
**Owner:** Sunneteam

---

## 1. What This System Does

Microsoft 365 Message Center publishes thousands of announcements every year. Only a fraction matter for Power Platform — Power Apps, Power Automate, Dataverse, Copilot for Power Platform — but a single missed breaking change can take down a production flow.

This solution runs entirely on Power Platform and:

1. Pulls every new MC announcement from a SharePoint mirror list (`MessageCenters`, ~86k historical records, ID range 10000–100xxx)
2. Strips HTML, hands the clean text to AI Builder (GPT-5 reasoning), expects strict JSON back
3. Stores the classified record on a second SharePoint list (`AdminList`)
4. Sends an email alert only when the verdict is `Status = Open` (action required)
5. Marks the source record as processed so the trigger does not re-fire

Cost target: ~30 AI credits and ~6.7 s per run. The whole pipeline is one Power Automate cloud flow with 9 named Scopes and a global Try/Catch.

---

## 2. Prerequisites

| Item | Requirement |
|---|---|
| Power Platform license | Per-user or per-flow plan with AI Builder capacity |
| AI Builder credits | ~30 credits per run — budget accordingly for backfill of historical data |
| SharePoint sites | Two sites (or one site with two lists) — one for source, one for Admin List |
| Service account | Dedicated account with OAuth 2.0 — used for both SharePoint and Outlook connections |
| Mailbox / Distribution List | `powerplatform-admins@[tenant].com` (or equivalent) for action-required alerts |
| Environments | Three separate Power Platform environments: DEV, TEST, PROD |

---

## 3. Initial Deployment

The solution ships as two `.zip` packages: a **managed** version for TEST and PROD, and an **unmanaged** version for DEV.

### 3.1 Prepare SharePoint

Create or confirm both lists.

**Source list — `MessageCenters`** (probably already exists if the tenant mirrors MC):

| Column | Type | Required |
|---|---|---|
| ID | Integer (PK) | Yes |
| Modified | DateTime | Yes |
| Created | DateTime | Yes |
| FullMessage | Multiline text (HTML, Latin1 encoded) | Yes |
| Processed | Yes/No | Yes (used by deduplication) |

**Target list — `AdminList`:**

| Column | Type | Required |
|---|---|---|
| SourceID | Integer | Yes |
| Title | Single line text | Yes |
| Category | Choice: Maintenance \| New Feature \| Breaking Change \| Other | Yes |
| Priority | Choice: High \| Medium \| Low | Yes |
| Impact | Choice: High \| Medium \| Low | Yes |
| Summary | Multiline text | No |
| ActionsTaken | Multiline text | No |
| Status | Choice: Open \| Closed | Yes |
| CreatedOn_Src | DateTime | No |
| ModifiedOn_Src | DateTime | No |

### 3.2 Connection References

Set up before importing the solution. Use the dedicated service account.

| Connector | Purpose | Auth |
|---|---|---|
| SharePoint (source) | Read trigger + update source item | OAuth 2.0 |
| SharePoint (target) | Create item in AdminList | OAuth 2.0 |
| Office 365 Outlook | Send "action required" emails | OAuth 2.0 |
| AI Builder | Run a Prompt | Built-in |

### 3.3 Environment Variables

| Variable | Example value (DEV) | Description |
|---|---|---|
| `SP_SourceSiteURL` | `https://[tenant].sharepoint.com/sites/[site]` | Site that hosts `MessageCenters` |
| `SP_TargetSiteURL` | `https://[tenant].sharepoint.com/sites/[adminsite]` | Site that hosts `AdminList` |
| `AdminEmailDL` | `powerplatform-admins@[tenant].com` | Recipient of action-required alerts |
| `AI_PromptName` | `MC_ClassificationPrompt` | Name of the AI Builder prompt |

### 3.4 Import and Activate

1. Import the **unmanaged** solution into DEV.
2. Bind environment variables and connection references during the import wizard.
3. Activate the `PP MC Auto-Analysis Flow`.
4. Run a smoke test on 5 representative items from `MessageCenters` (one per category).
5. Export the solution as **managed**, import to TEST, repeat the smoke test, then promote to PROD.

---

## 4. Day-2 Operations

### 4.1 Health Checks

| Signal | Where to look | What it means |
|---|---|---|
| Flow run history | Power Automate > My flows > Run history | Look for failed runs in the last 24h — investigate the Error Handling scope output |
| AdminList growth | SharePoint AdminList | Should grow with each new MC item. No growth in 24h+ on a working tenant = trigger or auth issue |
| Email alerts | Inbox of `AdminEmailDL` | Sparse, only for `Status = Open` items |
| AI credit consumption | Power Platform Admin Center > Capacity | Burn rate should be roughly `(new MC items per day) × 30 credits` |

### 4.2 Common Operational Tasks

**Replay a misclassified item:**
1. Open the AdminList record and note the `SourceID`.
2. Toggle `Processed = false` on the source `MessageCenters` item.
3. Edit the source item (no value change needed) to refire the trigger.
4. The dedup gate is bypassed since `Processed` is now false.
5. Confirm a new AdminList record is created with the updated classification.

**Bulk-backfill historical messages:**
1. Filter the source list by date range (start small — 100 items).
2. Set `Processed = false` on the batch.
3. Trigger a flow run on each item programmatically (Power Automate Desktop or a one-off script).
4. Monitor AI credit burn — 100 items ≈ 3000 credits.

**Update the system prompt:**
1. Open the AI Builder prompt `MC_ClassificationPrompt` in DEV.
2. Make changes; test against 10 representative items before saving.
3. Export the solution as managed, promote to TEST → PROD.
4. Run the smoke-test suite in each environment.

### 4.3 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Flow fails on Step 5 with "Invalid JSON" | LLM returned Markdown fences or prose around JSON | Tighten the system prompt: "Return ONLY valid JSON, no preamble, no Markdown". Optional: add a JSON-repair Compose step before Parse JSON |
| Trigger fires twice for the same item | Concurrent edits on the source list | Confirm Step 3 (dedup gate) is running and `Processed` is being set in Step 8 |
| AI credit burn higher than expected | Backfill running or trigger loop | Check flow run history for items processed >1 time; tighten Step 3 condition |
| Email alerts not delivered | Service account license expired or DL changed | Verify `AdminEmailDL` env variable, test Outlook connection |
| HTML cleanup leaves garbage | Older MC items use legacy HTML | Add a second pass: regex to strip residual `<style>`/`<script>` blocks in Step 4 |

### 4.4 Known Limitations

1. AI Builder may misclassify short/ambiguous messages — run a manual review of `Category = Other` items weekly.
2. The 86k historical-record list can stall the first run — filter by date when testing.
3. AI Builder is English-optimised; non-English MC items may need a translate step.
4. The system **identifies and notifies only** — there is no auto-remediation. Acting on alerts is the administrator's responsibility.

---

## 5. ALM and Change Management

- All changes go through DEV → TEST → PROD with the managed solution package
- Environment variables are bound at import time — never hard-code values
- Test the regression suite (5 representative items, one per category) after every promotion
- The system prompt is the most volatile asset — version it explicitly and keep the previous version exportable for rollback

---

## 6. Where Things Live

| Asset | Location |
|---|---|
| Cloud flow | Power Automate > Solutions > PP MC Auto-Analysis |
| AI prompt | AI Builder > Prompts > `MC_ClassificationPrompt` |
| Source list | SharePoint > `MessageCenters` |
| Target list | SharePoint > `AdminList` |
| Technical doc | `PP_MessageCenter_TechDoc_EN.docx` |
| Sprint reports | Sunneteam repository / WRO-BOOST share |

---

## 7. Escalation

1. **Tier 1 — Flow run failure**: Check the Error Handling scope output in the failed run. Most issues resolve here.
2. **Tier 2 — AI/Prompt regression**: Open the prompt in AI Builder, test against the regression set, revert if needed.
3. **Tier 3 — Architectural changes** (new fields, new category, additional connectors): Goes through the change-management process — DEV first, code review, regression suite, then promote.

For questions beyond this guide, reach out to the Sunneteam contact list in the technical documentation.
