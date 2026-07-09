---
name: generate-report
description: Compiles a progress report of all scraping runs logged in next_report.md, detailing outliers, potential matches, and drafted resumes.
---

# Generate Report Skill

This skill compiles your progress report. It references the `next_report.md` ledger to analyze all scraping queries, niches, and evaluations performed since the last run.

## Instructions

1. **Read Ledger:**
   - Open the `[[next_report]]` file (located at the root of the wiki: `next_report.md`).
   - Identify all search queries (and their respective search report paths) registered since the last report cycle.

2. **Gather Evaluated Jobs:**
   - Scan the referenced search report files to extract the niches, query criteria, and initial triage scores.
   - Scan the corresponding individual files in `raw/.scraped-jobs/jobs/` to read the detailed scores, rationales, and current statuses.

3. **Map Resumes & Applications:**
   - Check the `applications/` folder for any tailored resume files (e.g., `Resume-[Company]-[JobTitle].md`) and tracking files.
   - For jobs that have active resume drafts, extract the filename and absolute/relative path of the drafted resume.

4. **Structure the Report:**
   - **Niche Grouping**: Group the entire report by **Niche**.
   - **Finalists & Resumes (Top Section)**: For each niche, list twice-promoted jobs (`#status/promoted-final` or `#status/resume-drafted`) first. Show their title, company, evaluation score, and include a direct link to the drafted resume file (e.g., `[[Resume-[Company]-[JobTitle]]`).
   - **Potential Matches (Middle Section)**: List jobs tagged `#status/potential` that are worth reviewing. Show their company, title, and evaluation score.
   - **Dismissed Jobs (Bottom Section)**: Briefly list dismissed jobs at the end of the document for completeness. Group them by **Niche** and the **Reason for dismissal** (e.g., tech mismatch, location, salary).

5. **Write Report:**
   - Save the compiled report as a new markdown log file (or append it to `log.md` if configured), using clean Obsidian-style links (no absolute paths) to connect back to the jobs, evaluations, and resumes.
   - Clear or archive the query items inside `next_report.md` so it is reset for the next scraping cycle.
