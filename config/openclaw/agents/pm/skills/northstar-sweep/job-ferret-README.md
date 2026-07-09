# Job Ferret MVP

A lightweight, Dockerized FastAPI service that wraps the [python-jobspy](https://github.com/Bunsly/JobSpy) library. Designed for AI agent consumption: run job searches, tag them with custom labels, persist everything in SQLite, and auto-generate interlinked Markdown reports and listings into a host-mounted directory.

---

## Agent Guide: How to Craft Effective Queries

This section is the most important part of this document. Read it before constructing any search request.

### Platform Quick Reference

| Platform | Rate Limiting | Best For | Key Constraint |
| :--- | :--- | :--- | :--- |
| **Indeed** | Almost none | High-volume scraping, precise Boolean queries | `hours_old`, `job_type`/`is_remote`, and `easy_apply` are **mutually exclusive** — pick ONE per query |
| **LinkedIn** | Aggressive (~10 pages before block) | Targeted company searches, `easy_apply` (broken upstream) | **Requires proxies** for anything beyond small scrapes. `linkedin_fetch_description` multiplies requests by O(n) |
| **ZipRecruiter** | Moderate | US/Canada jobs only | Rounds `hours_old` up to nearest day. Ignores `job_type`/`is_remote` |
| **Glassdoor** | Moderate | International searches (same countries as Indeed) | Requires `country_indeed` parameter |
| **Google Jobs** | Low | Hyper-specific niche searches | Ignores ALL standard filters. Only `google_search_term` works |
| **Bayt** | Low | Middle East / international | Only uses `search_term`, ignores all other filters |

> **Global cap**: All job boards cap results at ~1,000 jobs per search regardless of `results_wanted`. Use `offset` to paginate through large result sets.

---


### Indeed
> Workhorse, great for testing

Indeed is the most reliable scraper — no rate limiting, rich data, and advanced Boolean search syntax. **Use Indeed as your default site.**

#### Boolean Search Syntax (Critical)
Indeed searches both title AND description, so unqualified terms return noisy results. Use these operators:

| Operator | Example | Effect |
| :--- | :--- | :--- |
| `"..."` | `"engineering intern"` | Exact phrase match |
| `-` | `-tax -marketing` | Exclude results containing these words |
| `OR` | `(java OR python OR c++)` | Match any of the grouped terms |
| `()` | `(senior OR lead) engineer` | Group terms for Boolean logic |

**Example of an optimized Indeed query:**
```
"engineering intern" software summer (java OR python OR c++) 2025 -tax -marketing
```
This searches title+description and requires "engineering intern" exactly, plus software, summer, 2025, at least one language, and excludes tax/marketing roles.

#### Indeed Filter Rules
Only **one** of the following filter groups can be active per Indeed query:
- `hours_old` (filter by posting age)
- `job_type` + `is_remote` (filter by job characteristics)
- `easy_apply` (filter for Indeed Apply — direct platform applications)

Combining them causes the scraper to error. Plan separate queries if you need different filters.

---

### LinkedIn
>Powerful but rate-limited

LinkedIn returns rich data (job level, company industry) but blocks aggressively.

#### Proxy Requirement
- **Without proxies**: Safe for ~10–20 results per query, maybe 2–3 queries per session before getting blocked.
- **With proxies**: Pass a list of rotating proxies to scale LinkedIn scraping. Scrapers round-robin through the list automatically.

```json
{
  "site_name": ["linkedin"],
  "search_term": "UX designer",
  "proxies": ["user:pass@proxy1.example.com:8080", "user:pass@proxy2.example.com:8080"],
  "results_wanted": 50,
  "linkedin_fetch_description": true
}
```

#### `linkedin_fetch_description`
By default, LinkedIn listings come back with truncated descriptions. Setting this to `true` fetches the full description and direct job URL, but makes **one additional HTTP request per job** — greatly increasing the chance of rate limiting. Only use with proxies.

#### `linkedin_company_ids`
Target specific employers by their numeric LinkedIn Company ID. This is useful for "watch list" monitoring (e.g., "alert me when Google, Apple, or Meta post new UX roles"):
```json
{
  "site_name": ["linkedin"],
  "search_term": "UX designer",
  "linkedin_company_ids": [162474, 1035, 10667],
  "results_wanted": 20,
  "proxies": ["user:pass@proxy1.example.com:8080"]
}
```
> Find Company IDs: Go to a company's LinkedIn page → view page source → search for `companyId`.

#### LinkedIn Filter Rules
Only **one** of the following can be used per LinkedIn query:
- `hours_old`
- `easy_apply` (note: LinkedIn easy apply filter is **broken upstream** in python-jobspy — may return unfiltered results)

---

### `easy_apply`: Direct Platform Applications

When `easy_apply: true`, the scraper can filter for jobs that can be applied to directly on the job board (e.g., Indeed Apply) without redirecting to external career portals (Workday, Greenhouse, Taleo, etc.).

| Platform | `easy_apply` Status |
| :--- | :--- |
| Indeed | ✅ Works reliably |
| LinkedIn | ⚠️ Broken upstream in python-jobspy — may not filter correctly |
| Others | ❌ Not applicable |

**Agent strategy**: If your downstream workflow involves automated applications, filter Indeed with `easy_apply: true` to get jobs with simple, standardized application forms.

---

### Google Jobs: Special Syntax Required

Google Jobs ignores `location`, `job_type`, `hours_old`, and all other standard parameters. The **only** way to search Google Jobs is:

1. Go to Google in a browser and search for jobs
2. Apply your desired filters in the Google Jobs UI
3. Copy the exact query string from the search box
4. Pass it as `google_search_term`

```json
{
  "site_name": ["google"],
  "google_search_term": "software engineer jobs near San Francisco, CA since yesterday"
}
```

---

### Pagination with `offset`

Use `offset` to paginate through large result sets across multiple API calls:

```json
{"search_term": "python", "site_name": ["indeed"], "results_wanted": 50, "offset": 0}
{"search_term": "python", "site_name": ["indeed"], "results_wanted": 50, "offset": 50}
{"search_term": "python", "site_name": ["indeed"], "results_wanted": 50, "offset": 100}
```

Each call returns a new batch of results starting from the offset. Use different labels (e.g., `"python-page-1"`, `"python-page-2"`) to keep reports organized.

---

### Proxy Configuration

Proxies are essential for LinkedIn and useful for high-volume scraping on any site. Pass them as a list — scrapers automatically round-robin through them:

```json
{
  "proxies": [
    "user:pass@residential1.example.com:8080",
    "user:pass@residential2.example.com:8080",
    "localhost:9050"
  ],
  "ca_cert": "/path/to/ca-cert.pem"
}
```

Use `ca_cert` only if your proxy provider requires a custom CA certificate for TLS interception.

---

## Supported Countries (Indeed & Glassdoor)

Pass the exact country name as `country_indeed`. Countries marked with `*` are also supported by Glassdoor.

|                      |              |            |                |
|----------------------|--------------|------------|----------------|
| Argentina            | Australia*   | Austria*   | Bahrain        |
| Belgium*             | Brazil*      | Canada*    | Chile          |
| China                | Colombia     | Costa Rica | Czech Republic |
| Denmark              | Ecuador      | Egypt      | Finland        |
| France*              | Germany*     | Greece     | Hong Kong*     |
| Hungary              | India*       | Indonesia  | Ireland*       |
| Israel               | Italy*       | Japan      | Kuwait         |
| Luxembourg           | Malaysia     | Mexico*    | Morocco        |
| Netherlands*         | New Zealand* | Nigeria    | Norway         |
| Oman                 | Pakistan     | Panama     | Peru           |
| Philippines          | Poland       | Portugal   | Qatar          |
| Romania              | Saudi Arabia | Singapore* | South Africa   |
| South Korea          | Spain*       | Sweden     | Switzerland*   |
| Taiwan               | Thailand     | Turkey     | Ukraine        |
| United Arab Emirates | UK*          | USA*       | Uruguay        |
| Venezuela            | Vietnam*     |            |                |

---

## Output Architecture & Obsidian Integration

All outputs are written to the `/app/data` mount (configured via Docker Compose volume).

### File Structure
```
data/
├── jobs.sqlite
├── reports/
│   └── 20260707_python-remote-test_1.md
└── listings/
    └── python-remote-test/
        ├── 20260707_software_engineer_a1b2c3d4.md
        └── ...
```

### Filename Conventions
- **Report**: `{YYYYMMDD}_{label}_{query_id}.md`
- **Listing**: `{YYYYMMDD}_{job_title}_{job_id}.md`
- **Timezone**: Set `TZ` in docker-compose to control the date prefix (default: `America/New_York`)

### Obsidian Wikilinks
Files cross-link using `[[filename]]` syntax inside the YAML frontmatter. Because Obsidian resolves by name, no absolute or relative directory paths are required:

#### Report frontmatter
Indexes the jobs under `results:` with detailed metadata and section highlights. Previews are structured under `Duties:`, `Tech:`, and `Exp:` categories:

```yaml
results:
  - id: "in-abc123def456"
    title: "Software Engineer"
    company: "Google"
    location: "Remote"
    compensation: "$150,000 - $200,000 USD yearly"
    link: "[[20260708_software_engineer_in-abc123def456.md]]"
    section: "[[#1. Software Engineer at Google (in-abc123def456)]]"
    url: "https://www.indeed.com/viewjob?jk=abc123def456"
    Duties:
      - "Design, develop, and maintain automated test scripts using Selenium or similar automation frameworks."
    Exp:
      - "Bachelor’s degree in Computer Science or related field (or equivalent experience)"
      - "5+ years of software testing/QA experience in Agile environments."
```

#### Listing frontmatter 
Links back to the query report:

```yaml
query_report:
  - "[[20260708_python-remote-test_1.md]]"
```


## Quick Start

```bash
cd job-ferret-mvp
cp .env.example .env       # Set TZ, HOST_PORT, LOG_LEVEL
docker-compose up --build -d
curl http://localhost:8000/health
```

### Test Search
```bash
curl -s -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "label": "python-remote-test",
    "search_term": "python developer",
    "location": "Remote",
    "site_name": ["indeed"],
    "results_wanted": 3,
    "country_indeed": "USA"
  }' | python3 -m json.tool
```

---

## Full API Reference

### `POST /search`

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `label` | string | `"default-scrape"` | Custom tag to categorize this query |
| `search_term` | string | **required** | Search keyword (supports Indeed Boolean syntax) |
| `site_name` | string or list | `["indeed"]` | `indeed`, `linkedin`, `zip_recruiter`, `glassdoor`, `google`, `bayt`, `naukri` |
| `location` | string | `null` | Job location (e.g. `"New York, NY"`, `"Remote"`) |
| `distance` | integer | `50` | Radius in miles from location |
| `results_wanted` | integer | `20` | Max results per site |
| `offset` | integer | `null` | Skip this many results (for pagination) |
| `hours_old` | integer | `null` | Only jobs posted within this many hours |
| `job_type` | string | `null` | `fulltime`, `parttime`, `internship`, `contract` |
| `is_remote` | boolean | `null` | Filter for remote jobs |
| `easy_apply` | boolean | `null` | Filter for direct-apply jobs (Indeed only — LinkedIn broken upstream) |
| `country_indeed` | string | `"USA"` | Country for Indeed & Glassdoor (see supported list above) |
| `google_search_term` | string | `null` | Search query for Google Jobs (only filter that works on Google) |
| `linkedin_fetch_description` | boolean | `false` | Fetch full LinkedIn descriptions (O(n) extra requests — use with proxies) |
| `linkedin_company_ids` | list of int | `null` | Filter LinkedIn results to specific company IDs |
| `enforce_annual_salary` | boolean | `false` | Normalize all wages to annual salary |
| `proxies` | list of string | `null` | Proxy list in `user:pass@host:port` format (round-robin) |
| `ca_cert` | string | `null` | Path to CA cert file for proxy TLS |
| `save_report` | boolean | `true` | Generate report file inside `/reports/` |
| `save_listings` | boolean | `true` | Generate individual job markdown files inside `/listings/` |

#### Response

Returns a lightweight receipt showing where the persisted report has been saved on the host. This minimizes response token usage, permitting the agent to inspect only the report's frontmatter rather than swallowing the entire result set in the initial JSON response payload.

```json
{
  "query_id": 1,
  "label": "python-remote-test",
  "timestamp": "2026-07-08 12:58",
  "count": 3,
  "report_file": "reports/20260708_python-remote-test_1.md"
}
```

### `GET /queries`
Returns recent query history. Optional `limit` param (default 20).

### `GET /health`
Returns `{"status": "ok", "service": "job-ferret-mvp"}`.

---

## Database Schema

### `queries`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER (PK) | Auto-increment ID |
| `timestamp` | TEXT | Local timestamp (`YYYY-MM-DD HH:MM`) |
| `label` | TEXT | Query label tag |
| `search_term` | TEXT | Search keyword |
| `location` | TEXT | Location filter |
| `site_names` | TEXT | Comma-separated site names |
| `results_wanted` | INTEGER | Requested count |
| `results_count` | INTEGER | Actual returned count |
| `raw_params` | TEXT | Full JSON of all parameters |
| `report_filename` | TEXT | Report markdown filename |

### `jobs`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | TEXT (PK) | Prefix + platform-native ID (e.g. `in-{jk}` or `li-{view_id}`), falling back to stable SHA-256 hash |
| `query_id` | INTEGER (FK) | Maps to `queries.id` |
| `site` | TEXT | Source job board |
| `title` | TEXT | Job title |
| `company` | TEXT | Company name |
| `job_url` | TEXT | Direct application URL |
| `description` | TEXT | Full Markdown description |
| `date_posted` | TEXT | Posting date |
| `min_amount` / `max_amount` | TEXT | Salary range |
| `currency` / `interval` | TEXT | Compensation details |
| `scraped_at` | TEXT | Local timestamp of scrape |
| `listing_filename` | TEXT | Individual job Markdown filename |

---

## Docker Compose Example

```yaml
services:
  job-ferret:
    build: .
    container_name: job-ferret-mvp
    ports:
      - "${HOST_PORT:-8000}:8000"
    volumes:
      - ./data:/app/data
    environment:
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - TZ=${TZ:-America/New_York}
      - DATA_DIR=/app/data # Optional: override the data directory
      # Preview verbosity for each listing
      - PREVIEW_DUTIES=${PREVIEW_DUTIES:-1}
      - PREVIEW_TECH=${PREVIEW_TECH:-1}
      - PREVIEW_EXP=${PREVIEW_EXP:-1}
    ports:
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 15s
```

---

## Upgrading to PostgreSQL

```yaml
environment:
  - DATABASE_URL=postgresql://user:pass@postgres-host:5432/dbname
```
Add `psycopg2-binary` to `requirements.txt` and rebuild with `docker-compose up --build -d`.

