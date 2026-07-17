---
name: "triage-reports"
description: "Performs rapid first-pass evaluation on newly ingested search reports to identify viable jobs without reading full job descriptions."
---

# triage-reports

---
name: "triage-reports"
description: "Performs rapid first-pass evaluation on newly ingested search reports to identify viable jobs without reading full job descriptions."
status: proposal
version: "v2"
date: "2026-07-14"
agent: "analyst-agent"
---

## Purpose

This skill is the first filter in the pipeline. It reads search report summaries and applies a rapid score to prevent junk jobs (in-person, low compensation, ghost jobs) from cluttering the deep evaluation queue. Evaluation is done purely from the summary frontmatter — individual job listing files are **not** read at this stage.

## Execution Trigger

- **Workboard dispatch**: Triggered when a parent report card's status becomes `ready`.
- Agent: `analyst-agent`

## Required Inputs

- `SCHEMA.md` — pipeline structure reference
- The search report file in `pipeline/inputs/searches/`
- The `label` from the search report frontmatter, which maps to the parent Niche file
- Summarized criteria knowledge from:
  - `strategy/criteria/criteria-traditional-fit.md`
  - `strategy/criteria/criteria-short-term-priorities.md`
  - `strategy/criteria/criteria-long-term-goals.md`
  - `strategy/criteria/criteria-employer-evaluation.md`

## Procedure

### 1. Data Ingestion

1. Read the unscored search report file from `pipeline/inputs/searches/`.
2. Observe the `label` in the frontmatter. Read the parent Niche file associated with that label (e.g., `niches/design-systems`) to understand the specific experiment goals.
3. Read the `results` array in the search report. **DO NOT read individual job listing files in `jobs/`.** Evaluation must be done purely using the summary frontmatter (Duties, Exp, title, compensation) inside the report.

### 2. First-Pass Scoring (Rapid Triage)

For each job in the `results` array, estimate a score across the core criteria:

- **Traditional Fit**: Do the summarized duties match the core background/compensation?
- **Short-Term Priorities**: Are there immediate red flags for remote work (e.g., "In-person", "fast-paced")? If in-person, score extremely low.
- **Long-Term Goals**: Is the title strategic or operational?
- **Employer Sanity**: Missing company name? Generic "entry level" with 5 yrs requirement? Known spam employer?
- **Niche Alignment**: Does the summary align with the experiment documented in the niche file?

Calculate a preliminary `overall` score out of 100 (or 1-10 scale).
Identify any critical `red_flags`.

### 3. Output Generation

1. **Update the Report**: Add a `scores` block to each job object directly within the search report file.
2. **Move the Report**: Move the scored report file from `pipeline/inputs/searches/` to `pipeline/active/searches/`.
3. **Move Priority Jobs**: If a job scores >= 7 (on 1-10 scale), physically move its file from `pipeline/inputs/jobs/<label>/` to `pipeline/active/jobs/`.

### 4. Workboard State (The Ledger)

1. Use `workboard_claim` to claim the parent report card.
2. Use `workboard_heartbeat` periodically during scoring if processing many jobs.
3. For each low-scoring job (< 7), use `workboard_delete` (or update status to rejected) for the corresponding child card.
4. Use `workboard_complete` on the parent report card. This automatically promotes the remaining child cards (the priority jobs) to `ready` status.

## Output Artifacts

| Artifact | Location |
|---|---|
| Scored search report | `pipeline/active/searches/<report>.md` (moved from `inputs/`) |
| Promoted job listings | `pipeline/active/jobs/<job>.md` (moved from `inputs/jobs/<label>/`) |
| Rejected child cards | Deleted from Workboard |
| Completed parent card | Workboard (status: `done`) |

## Error Handling

- If the search report file is missing or malformed, use `workboard_block` on the parent card with a descriptive error message.
- If the parent niche file cannot be found for the label, proceed with triage using only the four criteria files (skip niche alignment scoring).
- If no jobs score >= 7, complete the parent card normally — all child cards will be deleted/rejected.

## State Transitions

```
Parent report card: ready → claimed (workboard_claim)
  → Search report read from pipeline/inputs/searches/
  → Each job scored against criteria using summary data only
  → Scored report moved to pipeline/active/searches/
  → Jobs >= 7 moved to pipeline/active/jobs/
  → Low-scoring child cards deleted from Workboard
  → Parent card completed (workboard_complete)
  → Remaining child cards auto-promoted to ready
```
