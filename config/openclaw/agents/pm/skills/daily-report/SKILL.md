---
name: "daily-report"
description: "Synthesizes pipeline activity into a daily briefing, summarizes experiment schedule status, and surfaces blocked items requiring user input."
---

# daily-report

---
name: "daily-report"
description: "Synthesizes pipeline activity into a daily briefing, summarizes experiment schedule status, and surfaces blocked items requiring user input."
status: proposal
version: "v2"
date: "2026-07-14"
agent: "pm-agent"
---

## Purpose

This skill manages the system's daily state synthesis. It queries Workboard metrics, tracks active experiment schedules, and presents critical decisions to the user. It ensures that no questions, verification gaps, or niche alerts fall through the cracks.

## Execution Trigger

- **Daily cron schedule** — this is the one skill triggered by cron, not workboard dispatch.
- Agent: `pm-agent`

## Required Inputs

- `SCHEMA.md` — pipeline structure reference
- Workboard API (`workboard_list`) — current state of all cards
- `active-experiments.md` — the control panel and scheduler
- Pipeline queue counts (number of files in `pipeline/inputs/searches/`, `pipeline/active/jobs/`, `pipeline/active/searches/`)

## Procedure

### 1. Data Synthesis & Manifest Review

1. Call `workboard_list` to fetch the status of all cards (`ready`, `todo`, `blocked`, `review`, `done`).
2. Count pipeline metrics based on completed workboard cards since the last report:
   - Queries run (search reports created)
   - Jobs triaged (reports processed)
   - Jobs promoted (moved to active)
   - Jobs evaluated (deep evaluation completed)
   - Resumes drafted (application packages created)
3. Open `active-experiments.md`. Summarize the state of the scheduler:
   - Identify which experiments are currently `active` vs `paused`.
   - Calculate which experiments are scheduled to run in the next 24 hours.
4. Extract all `blocked` cards from the Workboard list. These represent:
   - Critical verification gaps (missing xp-wiki claims needing user answers)
   - Niche alerts (experiments hitting failure thresholds)
   - Any other items requiring user input
5. Scan `pipeline/active/jobs/` and summarize the highest-scoring jobs waiting for resume drafting.

### 2. Report Generation

Generate the Daily Northstar Briefing markdown file with this structure:

```markdown
# Northstar Daily Briefing — YYYY-MM-DD

## Executive Summary
<2-3 sentence overview of pipeline health and key items>

## Pipeline Metrics
| Stage | Count |
|---|---|
| Searches run | N |
| Reports triaged | N |
| Jobs promoted | N |
| Jobs evaluated | N |
| Resumes drafted | N |

## Experiment Status
<Summary of scheduler state from active-experiments.md>
- Which queries ran today
- Which are due tomorrow
- Any paused experiments

## Top Evaluated Jobs
<Highest-scoring jobs in pipeline/active/jobs/ awaiting resume drafting>

## 🚨 Action Required
- [ ] <Blocked card description — user question or verification gap>
- [ ] <Niche alert — experiment health warning>
```

Save this file to `pipeline/archive/reports/YYYY-MM-DD-northstar-report.md`.

### 3. Log Rotation & Rollover

*Note: Flat file rotation and task carry-over are handled natively by the Workboard SQLite state. No manual log rotation needed.*

Workboard `blocked` cards persist until resolved — they automatically carry forward across daily reports. The report simply queries current state each run.

### 4. Delivery

1. (Optional) Dispatch the generated briefing report to the user via Discord webhook or terminal message.
2. The report file in `pipeline/archive/reports/` serves as the persistent record.

## Output Artifacts

| Artifact | Location |
|---|---|
| Daily briefing report | `pipeline/archive/reports/YYYY-MM-DD-northstar-report.md` |
| (Optional) Discord/terminal notification | Configured webhook or stdout |

## Error Handling

- If `workboard_list` fails, generate a degraded report noting the Workboard is unreachable. Use file-system counts from pipeline directories as fallback metrics.
- If `active-experiments.md` is missing or malformed, skip the Experiment Status section and note the issue in Executive Summary.
- Always generate a report file even if partial — a degraded report is better than no report.

## State Transitions

```
Cron fires daily
  → workboard_list queried for all card statuses
  → active-experiments.md read for scheduler state
  → Pipeline directories scanned for queue counts
  → Briefing report generated with metrics, experiments, blocked items
  → Report saved to pipeline/archive/reports/
  → (Optional) notification dispatched
```
