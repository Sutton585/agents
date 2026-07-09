---
name: evaluate-jobs
description: Takes promoted jobs above the threshold, reviews their individual files in the jobs directory against full criteria text, and updates them with detailed scores and rationales.
---

# Evaluate Jobs Skill

This skill processes the initial outliers identified in the search report. For any job scoring above the threshold, it evaluates the individual job file in the `jobs/` folder using your fully-detailed criteria.

## Instructions

1. **Identify Queue:**
   - Read the recently updated search reports in `raw/.scraped-jobs/searches/` to find jobs marked as `#status/promoted-initial` (those scoring above the threshold).
   - Find the corresponding individual job markdown file under `raw/.scraped-jobs/jobs/[job-id].md`.

2. **Run Detailed Evaluation:**
   - Open and read the target job file `raw/.scraped-jobs/jobs/[job-id].md` to get its full description.
   - Load and read the full text of your detailed scoring files in `[[criteria]]` (e.g., `criteria/trad_score.md`, `criteria/agency_score.md`, etc.) and the target niche rubric in `[[niches]]`.

3. **Calculate and Log Detailed Scores:**
   - Evaluate the job description point-by-point against the rubrics.
   - Calculate the 5 core scores: `trad_score`, `agency_score`, `leverage_score`, `employer_score`, and `niche_score`.
   - Calculate the `overall` score and `viability` score using the formulas in `[[SCHEMA]]`.

4. **Update Job File:**
   - Write the detailed scores directly into the frontmatter of the job file `raw/.scraped-jobs/jobs/[job-id].md`.
   - Append a detailed **Rationale** section in the body of the markdown file explaining the scoring decisions.

5. **Final Tagging & Queue Handoff:**
   - Update the status tag in the job file:
     - **Double-Promoted (Finalist)**: If the final evaluation score is exceptionally high, tag as `#status/promoted-final`. (This queues it for the `draft-resume` skill).
     - **Potential Fit**: If it is a good fit but not top priority, tag as `#status/potential`.
     - **Dismissed**: If detailed criteria reveal a dealbreaker, tag as `#status/dismissed`.
