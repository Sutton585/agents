---
name: "scrape-jobs"
description: "Checks active-experiments.md manifest, determines which search queries are due, executes them via job-ferret, and updates execution timestamps."
---

# scrape-jobs

---
name: "scrape-jobs"
description: "Checks active-experiments.md manifest, determines which search queries are due, executes them via job-ferret, and updates execution timestamps."
status: proposal
version: "v2"
date: "2026-07-14"
agent: "scout-agent"
---

## Purpose

This skill is the ingestion engine for Project Northstar. It uses the `active-experiments.md` scheduler manifest to automate periodic job scrapes without exceeding rate limits or generating duplicate data. It produces raw search reports and individual job listing files, then creates Workboard cards to track downstream dependencies.

## Execution Trigger

- **Workboard dispatch**: Triggered by workboard dispatch to `scout-agent` (or manual request).
- Runs on a daily cron schedule or via manual invocation.

## Required Inputs

- `active-experiments.md` — the control panel and scheduler (vault root)
- `SCHEMA.md` — pipeline structure reference
- Access to the `job-ferret` API (`https://jobferret:8000/search`)

## Procedure

### 1. Schedule Verification

1. Open `active-experiments.md` from the vault root.
2. Read the `experiments` list in the YAML frontmatter.
3. For each experiment entry:
   - Verify `status` is `active`.
   - Calculate if due: `current_date - last_run >= interval_days`.
4. Identify all due experiments. If none are due, end execution early.

### 2. Execution

For each due experiment:

1. Extract parameters: `label`, `query`, and the destination niche link.
2. Send a POST request to the `job-ferret` API:
   ```json
   {
     "label": "<label>",
     "search_term": "<query>",
     "location": "Rochester, NY",
     "distance": 75,
     "results_wanted": 20
   }
   ```
3. Verify API executed successfully. Outputs are saved to:
   - `pipeline/inputs/searches/` — search report files
   - `pipeline/inputs/jobs/<label>/` — individual job listing files

### 3. Manifest Update

1. Update `last_run` date for each executed experiment in the YAML frontmatter of `active-experiments.md` to today's date.
2. Update the corresponding "Last Run" date in the user-readable list in the body of `active-experiments.md`.

### 4. Workboard State (The Ledger)

1. Use `workboard_create` to spawn a **parent card** for the search report:
   - Type: `search_report`
   - Status: `ready`
2. For each job found in the search report, use `workboard_create` to spawn a **child card**:
   - Type: `job_evaluation`
   - Status: `todo`
3. Use `workboard_link` to set each child job card as depending on the parent report card. This ensures jobs are blocked until the parent report is triaged.

## Output Artifacts

| Artifact | Location |
|---|---|
| Search report file | `pipeline/inputs/searches/<timestamp>_<label>.md` |
| Individual job listings | `pipeline/inputs/jobs/<label>/<job-id>.md` |
| Parent workboard card | Workboard (type: `search_report`, status: `ready`) |
| Child workboard cards | Workboard (type: `job_evaluation`, status: `todo`) |
| Updated manifest | `active-experiments.md` (updated `last_run`) |

## Error Handling

- If `job-ferret` API returns an error, do **not** update `last_run`. Log the failure and retry on next scheduled run.
- If no experiments are due, exit cleanly with no side effects.
- Use `workboard_block` if a systemic issue prevents scraping (e.g., API down, proxy failure).

## State Transitions

```
active-experiments.md checked → due experiments identified
  → job-ferret API called per experiment
  → outputs land in pipeline/inputs/
  → workboard cards created (parent: ready, children: todo)
  → manifest updated with today's date
```

## job-ferret Query Crafting Reference

### Platform Quick Reference

| Platform | Rate Limiting | Best For | Key Constraint |
|---|---|---|---|
| **Indeed** | Almost none | High-volume, Boolean queries | `hours_old`, `job_type`/`is_remote`, and `easy_apply` are mutually exclusive |
| **LinkedIn** | Aggressive | Targeted company searches | Requires proxies for scale |
| **ZipRecruiter** | Moderate | US/Canada only | Rounds `hours_old` to nearest day |
| **Glassdoor** | Moderate | International | Requires `country_indeed` param |
| **Google Jobs** | Low | Hyper-specific niche | Only `google_search_term` works |

### Indeed Boolean Syntax

| Operator | Example | Effect |
|---|---|---|
| `"..."` | `"engineering intern"` | Exact phrase match |
| `-` | `-tax -marketing` | Exclude terms |
| `OR` | `(java OR python OR c++)` | Match any grouped term |
| `()` | `(senior OR lead) engineer` | Group for Boolean logic |

### Indeed Filter Rules

Only **one** of the following filter groups per query:
- `hours_old` (posting age)
- `job_type` + `is_remote` (job characteristics)
- `easy_apply` (Indeed Apply)

Combining them causes errors. Plan separate queries if multiple filters are needed.
