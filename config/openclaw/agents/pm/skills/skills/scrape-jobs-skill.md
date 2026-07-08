---
name: scrape-jobs
description: Triggers the Job Ferret API scrape, records the query in next_report.md, and performs initial prioritization by scoring jobs in the search report frontmatter.
---

# Scrape Jobs Skill

This skill triggers your external scraping tool, registers the search query for report generation, and executes a first-pass scoring phase to identify which jobs to queue for full evaluation.

## Instructions

1. **Trigger Scrape:**
   - Make an HTTP call to the Job Ferret API at `http://job-ferret:3333` (e.g., using `curl` or an HTTP request tool) to trigger the scrape query.
   - This API call will output a search report markdown file into the hidden folder `raw/.scraped-jobs/searches/` (e.g., `raw/.scraped-jobs/searches/query-[timestamp].md`).

2. **Register Search Query:**
   - Immediately open the `[[next_report]]` file (located at the root of the wiki: `next_report.md`).
   - Append the filename of the newly generated search report (e.g., `[[raw/.scraped-jobs/searches/query-[timestamp].md]]`), the query parameters, targeted niche, and general criteria parameters to the tracking log in `next_report.md`.

3. **First-Pass Prioritization:**
   - Open the new search report file.
   - Scan the frontmatter or list of jobs contained in this report.
   - For each job description listed in the report, read its full body text.
   - Apply a quick initial evaluation using the rules in `[[criteria]]` and the targeted `[[niches]]` (specifically focusing on core requirements like tech stack, location, and salary).

4. **Assign Initial Scores:**
   - Calculate initial scores for the jobs.
   - Write these scores directly into the frontmatter of the search report file (e.g., mapping job IDs to initial scores: `job_123: 78`, `job_124: 55`).
   - Flag any job that scores above your threshold (e.g., $\ge 75$) for promotion. Mark it in the report as `#status/promoted-initial`. Dismiss the rest with `#status/dismissed`.
