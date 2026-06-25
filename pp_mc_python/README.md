# pp-mc-python — Python equivalent of the PP Message Center Auto-Analysis flow

A 1:1 Python re-implementation of the Power Automate cloud flow described in `PP_MessageCenter_TechDoc_EN.docx`. Same 9 stages, same dedup gate, same global error-handling scope, same JSON schema out.

## Why this exists

The original solution is fully governed by Power Platform. This Python project is useful when:

- You want to run the same pipeline outside the tenant — for example, as an Azure Function or a scheduled Container job
- You want to test prompt changes against thousands of historical records without burning AI Builder credits via the flow
- You want to integrate the classifier into a non-Power-Platform stack

## Architecture mirror

| Power Automate step | Python module |
|---|---|
| 1. Trigger (SharePoint item created/modified) | `sources.sharepoint.poll_changes` |
| 2. Initialize variables | dataclass `FlowContext` |
| 3. SCOPE: Check If Needs Processing | `pipeline.dedup_gate.is_processed` |
| 4. SCOPE: Clean Message | `pipeline.clean.html_to_text` |
| 5. SCOPE: AI Classification (The Brain) | `pipeline.classify.run_prompt` + `parse_json_strict` |
| 6. SCOPE: Store in Admin List | `sinks.admin_list.create_item` |
| 7. SCOPE: Notify if Action Required | `notify.email.send_alert` |
| 8. SCOPE: Update Original Item | `sources.sharepoint.mark_processed` |
| 9. SCOPE: Error Handling | `pipeline.errors.global_handler` + structured logs |

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then edit with your values
python -m pp_mc_python.main --once   # process pending items and exit
python -m pp_mc_python.main --watch  # poll continuously
```

## Layout

```
src/pp_mc_python/
  main.py               # CLI entry point - orchestrates all 9 stages
  context.py            # FlowContext dataclass (step 2 equivalent)
  pipeline/
    dedup_gate.py       # Step 3
    clean.py            # Step 4
    classify.py         # Step 5 (the brain)
    store.py            # Step 6
    notify.py           # Step 7
    update_source.py    # Step 8
    errors.py           # Step 9 (global handler)
  sources/
    sharepoint.py       # SharePoint REST adapter (source list)
  sinks/
    admin_list.py       # SharePoint Admin List writer
    email.py            # SMTP / Graph mail sender
  config.py             # env-var loading (mirrors Power Platform env vars)
  models.py             # ClassificationResult, MCItem dataclasses
tests/
  test_clean.py
  test_classify.py
  test_dedup.py
  test_pipeline.py
```

## Configuration

The Python project reads exactly the same configuration values as the Power Platform Environment Variables. See `.env.example`.

| Env var | Power Platform equivalent |
|---|---|
| `SP_SOURCE_SITE_URL` | `SP_SourceSiteURL` |
| `SP_TARGET_SITE_URL` | `SP_TargetSiteURL` |
| `ADMIN_EMAIL_DL` | `AdminEmailDL` |
| `AI_PROMPT_NAME` | `AI_PromptName` |
| `OPENAI_API_KEY` | (managed by AI Builder in PP) |
| `SP_CLIENT_ID` / `SP_CLIENT_SECRET` | (managed by Connection Reference in PP) |

## Running the regression set

```bash
pytest -v
```

Six scenarios mirroring the validation table from the technical doc: Maintenance, New Feature, Breaking Change, Unclear, Duplicate, Invalid JSON (negative).

## License & ownership

Sunneteam. Same license as the parent Power Platform solution.
