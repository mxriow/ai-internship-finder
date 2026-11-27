# ch-intern-finder

Finds current **internship postings for business roles in Switzerland, the Netherlands, Luxembourg, the UAE,
Belgium, Germany, the United Kingdom, Austria and Ireland**:
marketing, brand, sales, commercial, e-commerce, marketing analytics, business development, strategy, consulting,
communications, plus operations, finance and HR. It reads the public job feeds that companies' applicant tracking
systems (ATS) already publish, and turns them into a daily-updated, filterable page.

- **Sources:** only public, unauthenticated feeds: the Greenhouse, Lever, Ashby, Recruitee, Personio, Workday,
  Oracle Recruiting Cloud, Taleo, Eightfold, BambooHR, HiBob and JOIN job APIs that the employers' own career sites
  call, Teamtailor's RSS feed, Abacus Umantis job list pages, plus careers sites that publish a sitemap with
  schema.org `JobPosting` data on each job page (JSON-LD on Phenom, softgarden, Avature and other sites, or
  SuccessFactors microdata).
  It never touches LinkedIn, Indeed, jobs.ch or any other aggregator. It doesn't log in, respects robots.txt
  exactly as RFC 9309 defines it (wildcards, longest match, one retry before an unreachable file means "disallow"),
  makes at most 2 requests/second per host and sends a descriptive User-Agent.
- **Deterministic:** classification uses keyword/regex rules in `config.yaml`. No LLM calls, no API keys, nothing to pay for.
- **Coverage:** 268 verified employer feeds (see `companies.yaml`) and 315 documented gaps, per country
  (see [`gaps.md`](gaps.md)).

## Quick start (local)

```bash
pip install -r requirements.txt
python -m finder run          # fetch all feeds (~5 min), update data/ and docs/
open docs/index.html          # or just double-click it
```

`docs/index.html` is a single self-contained file with the data embedded. It works offline and when opened
straight from disk.

## Outputs

| File | What it is |
|---|---|
| `docs/index.html` | The viewer (details below). |
| `data/user_state.json` | Optional. Your exported hidden/starred/applied marks, applied for everyone when the page is built (see below). |
| `data/descriptions/` | The plain-text job description of every matching internship, one JSON file per feed (`<provider>/<token>.json`). Saved when a posting is first seen, refreshed when the text changes, and **kept after the posting closes**, so you can reread it before an interview. An empty description never overwrites a saved one. Kept out of `jobs.json` so that file stays small. |
| `data/jobs.json` | Every matching internship ever seen, keyed `provider:token:job_id`, with `first_seen`, `last_seen` and `status`. A posting is marked `closed` only after it is missing in **2 consecutive** successful runs. |
| `data/new_today.md` | Postings that first appeared in the latest run, grouped by company. |
| `data/review.md` | Borderline cases: category unclear, or an internship whose location could not be placed. These are kept, not dropped. |
| `data/last_run.json` | Run statistics, per-company counts and any feed failures. |
| `companies.yaml` | Verified employers: name, provider, token, careers_url, verified_at, current job counts, and the evidence used to verify them. |
| `gaps.md` / `gaps.yaml` | In-scope employers on unsupported systems, per country, each with a checked careers URL. The Swiss **top 30 to check by hand** come first. |

## Using the viewer

`docs/index.html` is one self-contained file. Double-click it; it needs no network.

- **Default view:** business categories only (marketing, brand, sales, business development, strategy,
  e-commerce/digital, commercial, marketing analytics, communications), English postings only, working-student
  roles hidden, open postings only. Each is a checkbox you can untick. Choosing a specific category, language or
  type in a dropdown overrides the matching checkbox.
- **Filters:** country (CH/NL/LU/AE/BE/DE/UK/AT/IE, any combination), city, category, language, company, type, and new in the last
  7 days. **Search** covers title and company. Click any column header to sort; the default is **Best fit**
  (see below), ties newest first. On a phone the rows become cards, the filters fold away, and a Sort menu replaces the headers.
- **Remembered filters:** the country selection and all other filters are saved in your browser and restored next
  time. On your first visit every country is on. "Reset filters" clears the saved settings.
- **Graduate programmes** (graduate schemes, early-career and young-professional programmes) are their own type,
  hidden by default ("Hide graduate programmes").
- **Requirements:** a *Degree* column (Bachelor OK / Master/MBA / ?; hover to see the sentence it is based on)
  and a *Languages* column (required languages, then `+` for "a plus"). Two toggles, both off by default:
  "Hide roles requiring a master's/MBA" and "Hide roles requiring fluent German/French/Dutch".
- **Start dates:** a *Start* column shows the start month the posting states ("Feb 2027"), ASAP, or blank when
  it doesn't say (hover for the exact phrase). Phrases in English, German, French, Dutch and Italian are
  recognised, e.g. "starting January 2027", "ab Februar 2027", "dès janvier", "per februari", "Start: 01.04.2027",
  "summer 2027", "Q2 2027". A month without a year means its next occurrence from today; seasons
  and quarters count from their first month (spring = March, summer = June, autumn = September, winter = January).
  Starts before April 2027 (and ASAP) get a small *before Apr* badge. The toggle "Hide roles that only start
  before April 2027" is off by default. The cut-off month is `early_start_before` in `config.yaml`.
- **Pay:** a *Pay* column shows the stated pay as gross EUR per month (annual figures /12, hourly rates x 173
  hours, marked ≈; CHF/GBP/AED at the fixed rates in `config.yaml` → `pay`). Hover shows the original text.
  Examples it reads: "€2.798 brutto", "EUR 1.617,- gross monthly", "Bruttomonatsgehalt", "min. € 1.070 per
  month", "1.050–2.270 €/Monat" (shown as a range, sorted by the lower end), "EUR 42.000 annual". When a
  posting gives one rate for voluntary and one for compulsory internships, the voluntary rate is the main
  figure and the compulsory one follows in brackets. Titles like "Compulsory Internship" / "Pflichtpraktikum"
  get a *compulsory only* badge. Sort by the Pay header (or "Highest pay" on a phone). The *Min. pay* box is
  empty by default; when set it hides postings below that amount, while postings that state no pay stay visible.
  Pay adds a small bonus to the fit score (≥ €1,000: +1, ≥ €1,500: +3, ≥ €2,000: +5; so the maximum is 105).
- **Possibly stale:** a posting whose stated start date, with its year, has already passed (e.g. "Start date:
  August 2026") gets a *possibly stale* badge; the role may be filled even though the page is still online.
  Graduation and application dates ("you will graduate between fall 2026 and …") are not start dates.
- **Copy for Claude:** every row (and every phone card) has a **Copy for Claude** button. One click copies
  plain text you can paste into Claude (or anywhere) to tailor a CV or prepare an interview:
  ```
  Acme AG: Marketing Intern
  Location: Zurich, Switzerland | Start: Feb 2027 | Pay: €2,100 gross per month | Deadline: 15 Dec 2026
  Link: https://…
  ---
  <the full job description>
  ```
  "Deadline" appears only when the description states one ("Application deadline: …", "Bewerbungsschluss …",
  "date limite …", "uiterlijk …"); Start and Pay say "not stated" when unknown. If no description was captured
  (e.g. Workday sitemap feeds), the text ends with "(Job description not captured; open the link.)". The button
  shows "Copied ✓". It uses the browser clipboard, falls back to the classic copy command, and as a last resort
  opens a box with the text selected for Ctrl+C / ⌘C. Descriptions are embedded in the page gzip-compressed
  and decoded in the browser (`DecompressionStream`: Chrome/Edge 80+, Firefox 113+, Safari 16.4+), for open
  postings and postings closed in the last 30 days (`viewer.embed_closed_days` in `config.yaml`). If the page
  would pass 12 MB, closed postings' descriptions are left out first. Older ones stay in `data/descriptions/`.
- **Per posting:** ☆ star (shortlist), ✓ applied, × hide, and "Hide company" (hides every posting from that
  employer). The **Starred / Applied / Hidden** buttons switch views. The Hidden view has Undo for each posting
  and each company. The counters show shown / starred / applied / hidden.
- **Where marks are saved:** in your browser's local storage, keyed by each posting's stable id, so they survive
  reloads and daily data updates. If storage is blocked (some private windows), the page still works and says so;
  use Export to keep your marks.
- **Export / Import:** Export downloads `user_state.json` with your hidden, hidden-company, starred and applied
  ids. Import loads such a file back (it adds to what you have), for example on another device or browser.

### Make hidden listings permanent (for every device and every daily rebuild)

1. In the viewer, hide/star/mark what you want, then click **Export state**. This saves `user_state.json`.
2. On GitHub, open the repo and go to the `data/` folder.
   - **First time:** click **Add file → Create new file** and name it `data/user_state.json`.
   - **Later:** click the existing `data/user_state.json`, then the pencil icon (**Edit this file**).
3. Open the exported file in a text editor, copy **all** of it, and paste it in as the file's entire content,
   replacing anything already there. Export always contains your complete current state.
4. Click **Commit changes…** and commit directly to `main`.
5. Run **Actions → Daily internship update → Run workflow**, or wait for the next daily run. The rebuilt page
   leaves out hidden postings and hidden companies, and shows starred/applied marks for everyone.

To un-hide something later, delete its id (or company name) from `data/user_state.json` and commit. A
malformed file is ignored with a warning, so it can never break the daily run. Locally,
`python -m finder build` applies the file without fetching anything.

### Best-fit score

The *Fit* column (0–100) scores each posting against one set of preferences; the default sort puts the highest
first. Five parts are added up. The points are in `config.yaml` under `fit_score`, so you can change what
counts most.

| Part | Points |
|---|---|
| Degree | bachelor OK **25** · unclear 15 · master's/MBA required 0 |
| Language the role needs | English only or English required **25** · needs German 10 · needs French or Dutch 5 (a posting written in German, French or Dutch counts as needing that language) |
| Category | brand, marketing, commercial, e-commerce/digital **25** · sales, strategy, marketing analytics/insights 15 · other business 5 · excluded 0 |
| Start | in or after April 2027, or not stated **15** · before April 2027 or ASAP 0 |
| Duration | 3–6 months **10** · not stated 6 · under 3 months 4 · over 6 months 0 (a range counts by its upper end, so "6–12 months" is "over 6") |

Example: a bachelor-friendly English brand internship starting May 2027 for 6 months scores 100. The same role
needing German and lasting 12 months scores 75. The score is computed when the page is built (`finder/fit.py`),
from the same Degree, Languages, Category, Start and Duration values the table shows.

## Daily automation with GitHub Actions

`.github/workflows/daily.yml` runs every day at 05:17 UTC and can also be started by hand. It runs the unit
tests, fetches all feeds, commits the updated `data/` and `docs/` back to the repo, and attaches the viewer to
the run as a downloadable artifact. Its token is limited to `contents: write` and `issues: write`.

**Alerts without email secrets.** At the end of every run a health check (`python -m finder health`) compares
the run with the previous one. The workflow opens an issue titled **"Internship finder needs attention"**, or
comments on it if it is already open, when:
- a step failed (tests, fetch, or publish), or
- more than 10% of the feeds failed, or
- the number of internships dropped by more than 40% compared with the previous run.

GitHub emails you about new issues and comments in your own repo (check *Settings → Notifications → Email* on
github.com if nothing arrives). The issue closes itself after the next healthy run.

**Monthly feed check.** `.github/workflows/monthly-verify.yml` runs `python -m finder verify` on the 3rd of
each month. It uses the same robots.txt rules and rate limit as the daily run, and only samples a few pages of
sitemap feeds. Feeds that error or return 0 jobs are listed in the same issue, under the label
`attention: verify`. A daily run doesn't close the issue while that label is on it. The next monthly check
that finds every feed working removes the label (or close it yourself once you've dealt with the feeds).
Run it any time from *Actions → Monthly feed check → Run workflow*.

### Repo settings to change (once)

1. **Settings → Actions → General → Actions permissions:** make sure Actions is enabled. "Allow all actions"
   works. If you restrict actions, allow GitHub-created actions, which covers `actions/checkout`,
   `actions/setup-python` and `actions/upload-artifact`.
2. **Settings → Actions → General → Workflow permissions:** select **"Read and write permissions"** and save.
   The workflow already asks for `contents: write` itself, which is normally enough. But if the commit step
   fails with `Permission to … denied to github-actions[bot]` (HTTP 403), this setting is the fix.
3. **Actions tab → "Daily internship update" → Run workflow** once, to check that it works. After that it runs
   on the schedule. Scheduled workflows only run from the default branch (`main`).

Cost: a daily run takes about 13–19 minutes, so roughly 450–550 minutes a month, plus about 20 for the
monthly check. That's inside the 2,000 free Actions minutes GitHub Free includes for private repositories.

### GitHub Pages and your private repo

- **GitHub Free:** Pages is **not available for private repositories**, so Pages will not work while the repo
  is private.
- **GitHub Pro / Team:** Pages works from a private repo, but the published site is **public on the
  internet** to anyone with the URL. Only GitHub Enterprise Cloud can restrict a Pages site to signed-in members.
- **If Pages is available and you're fine with a public URL:** Settings → Pages → Source "Deploy from a
  branch" → Branch `main`, folder `/docs` → Save. The page appears at
  `https://<user>.github.io/ch-intern-finder/` and refreshes after every daily commit.

(Check GitHub's current [Pages plan availability](https://docs.github.com/pages/getting-started-with-github-pages/about-github-pages),
as plans change.)

**Fallback for a private repo without Pages** (no extra setup needed). Any of these works:

- **Pull and open:** `git pull`, then double-click `docs/index.html`. It's fully self-contained.
- **Download from the run:** Actions tab → latest run → **Artifacts → `ch-intern-finder-viewer`**. Unzip it and
  open `index.html`. Artifacts are kept for 14 days.
- **Download from the repo:** on GitHub, open `docs/index.html` → "Download raw file", then open it locally.
  GitHub doesn't render HTML in the repo view.

## How to add a company

1. **Detect the feed** from the company's careers page:
   ```bash
   python -m finder discover "Acme AG" https://www.acme.ch/careers
   ```
   This scans the page, and up to three linked job pages, for Greenhouse / Lever / Ashby / Recruitee /
   Personio / Workday / Oracle Recruiting Cloud / Taleo / Eightfold / Teamtailor / BambooHR / HiBob / JOIN /
   Umantis / softgarden / Avature links, and for Phenom, SuccessFactors and Teamtailor page markers. If it finds none, it tries slugs derived from the name for Greenhouse, Lever, Ashby, Recruitee
   and Personio; a slug guess only counts if the board name matches exactly or the board has postings in the
   target countries. Workday, Oracle, Taleo and Eightfold tenants are never guessed. As a last resort it checks
   the careers host's own sitemap for job pages with JSON-LD. Sitemap-based feeds are verified on a sample of
   12 job pages. If you already know a feed URL, put it in a seeds file under `urls:` (see `seeds/`).
2. **Add it** when the output shows a feed with postings in the target countries:
   ```bash
   python -m finder discover "Acme AG" https://www.acme.ch/careers --add
   ```
   This writes the entry to `companies.yaml`, or to `gaps.yaml` if no supported feed is found. A company is only
   added after a real successful response with at least one posting in a target country (the seed's `country`,
   default CH, is recorded as its home market). Mark a seed `swiss_hq: true` to keep a Swiss-headquartered
   employer whose board is temporarily empty.
3. **Check and run:**
   ```bash
   python -m finder verify --only "Acme"   # confirms the feed still returns jobs
   python -m finder run --only "Acme"      # fetch just this company
   python -m finder gaps                   # re-render gaps.md (add --check-urls to re-test careers URLs)
   ```

Batch mode: `python -m finder discover --from-file seeds/my_list.yaml --add`. The format is in `seeds/*.yaml`:
`name`, `careers_url`, `sector`, optional `country`, `tokens`, `urls`, `swiss_hq`.

**Workday companies with several sites.** Many employers keep internships on a separate campus site. Add it under
`extra_sites:` next to `site:`; the tenant's robots.txt lists its public sites. Example:
`{name: PwC, provider: workday, token: pwc, host: pwc.wd3.myworkdayjobs.com, site: Global_Experienced_Careers, extra_sites: [Global_Campus_Careers]}`.

**Careers sites with a sitemap + JSON-LD** (no ATS API needed). If the job pages carry schema.org `JobPosting`
data, add the employer with:
```bash
python -m finder add-jsonld "Kuehne+Nagel" kuehnenagel https://jobs.kuehne-nagel.com/global/en/sitemap_index.xml \
    --url-filter '/job/' --id-pattern '/job/([^/]+)/' --add
```
- The command checks a sample of job pages live, and only adds the employer if `JobPosting` data is found.
- Pick the sitemap from the site's robots.txt.
- `--id-pattern` collapses locale copies of the same job, and `--prefer '/en/'` picks the English copy.
- Job pages are cached in `data/cache/jsonld/`, so later runs only fetch new or changed pages, at most
  `max_new` (default 300) per run.

**SAP SuccessFactors career sites** (job URLs look like `/job/<City>-<Title>/<id>/`) use the same command with
`--provider successfactors`:
```bash
python -m finder add-jsonld --provider successfactors "Swiss Re" swissre-sf https://careers.swissre.com/sitemap.xml --add
```
- The job pages carry schema.org microdata.
- URLs whose slug names no target-country place are never fetched, and internship-looking URLs are fetched
  first.
- Each employer gets a time budget per run (`budget_seconds`, default 480) that honours the site's
  robots.txt `Crawl-delay`. A large site fills its cache over several days instead of slowing the daily run.

**Oracle Recruiting Cloud, Taleo, Eightfold and Phenom** are detected by `discover` (see step 1); the entries
look like this:
- `{provider: oracle, token: ibqbjb, host: ibqbjb.fa.ocs.oraclecloud.com, site: CX_1}`. This reads the
  `recruitingCEJobRequisitions` API that the Candidate Experience page calls. Descriptions are fetched only
  for internship-like titles in target countries.
- `{provider: taleo, token: easyjet, host: easyjet.taleo.net, section: "2"}`. This reads the career section's
  job-board search; the portal id is taken from the section page. There are no descriptions.
- `{provider: eightfold, token: mlp, host: career.mlp.com, domain: mlp.com}`. This makes one query per target
  country. Several Eightfold tenants (AstraZeneca, Morgan Stanley, Boston Scientific, Estée Lauder, Deutsche
  Telekom) answer 403 to automated requests and stay in `gaps.md`.
- `{provider: phenom, token: careers-abb-ph, host: careers.abb}`. This reads the English sitemaps listed in
  robots.txt plus the JSON-LD on job pages. Phenom URLs end in the job title, so only internship-, working-student-,
  trainee- and graduate-titled pages are fetched (`all_pages: true` fetches all). Phenom's own `/api/apply` is
  disallowed by robots.txt and isn't used.

**Job systems added in 2026-11 (Teamtailor, BambooHR, HiBob, JOIN, Abacus Umantis, softgarden, Avature)** are detected
by `discover` from links on the careers page; the entries look like this:
- `{provider: teamtailor, token: axpo, host: careers.axpo.com}`. Reads the RSS feed every Teamtailor career site
  publishes at `/jobs.rss` (one request; full descriptions, city and country). Works on `*.teamtailor.com` and on
  the employer's own domain (detected from Teamtailor's page assets).
- `{provider: bamboohr, token: clearspace}`. Reads `<token>.bamboohr.com/careers/list` (the JSON the careers page
  loads); the description comes from `/careers/<id>/detail`, fetched only for internship-like titles.
- `{provider: hibob, token: synpulse}`. Reads `<token>.careers.hibob.com/api/job-ad`, the JSON the careers page loads
  (one request, descriptions included).
- `{provider: join, token: taurusgroup}`. Reads the job list embedded in `join.com/companies/<token>`; descriptions
  from the job page's JSON-LD, internship-like titles only.
- `{provider: umantis, token: kpmg-ch, host: recruitingapp-2791.umantis.com}`. Reads the public list page
  `/Jobs/All` (10 jobs per page, follows the next-page link). Job pages are a JavaScript app, so there is no
  description.
- **softgarden** and **Avature** need no provider of their own: softgarden's `<company>.softgarden.io/sitemap.xml`
  lists the job pages, which carry JSON-LD, so they are read by `jsonld`; for Avature, `discover` takes the
  sitemaps the portal's robots.txt allows.

**Checked and not supported** (recorded in `gaps.yaml` with the reason):
| System | Why not |
|---|---|
| iCIMS | `robots.txt` on `*.icims.com` portals is `Disallow: /` for all bots. |
| Workable | The public widget/job API answers HTTP 429 with a ~13-hour `Retry-After` to automated requests (Cloudflare). |
| Cornerstone OnDemand (csod.com) | The job search API needs a session token issued by the page; no public feed. |
| Pinpoint | `robots.txt` disallows `postings.json`. |
| onlyfy (XING/prescreen) | No feed, sitemap or structured job data. |
| SmartRecruiters | `api.smartrecruiters.com/robots.txt` disallows all bots (unchanged). |
| Radancy/TalentBrew, Paradox, Beamery, JobTeaser | No public feed found. |
| Jobvite, rexx, d.vinci, Personio XML variants, Breezy | None of the gap companies uses them (nothing to verify against), so no provider was built. |

For every sitemap crawler (jsonld, phenom, successfactors), when a site has more new pages than one run fetches,
pages whose URL names a target-country place or an internship go first.

You can also add an entry by hand to `companies.yaml`, for example
`{name, provider: workday, token: <tenant>, host: <tenant>.wd3.myworkdayjobs.com, site: <Site>}`. Then run
`verify`.

## How classification works (all in `config.yaml`)

- **Internship:** matched on word boundaries in the title, so *internal*, *international* and *internet*
  never match. Terms covered:
  - intern, internship, Praktikum/Praktikant\*in, Stage/Stagiaire, Tirocinio, Stagista
  - Dutch: stagiair(e), afstudeerstage, meewerkstage, stageplaats, traineeship ("Stage Manager" does not match)
  - Summer Analyst, Off-cycle
  - Working Student/Werkstudent (tagged `working_student`), Trainee (tagged `trainee`)
  - the feed's own employment type, where it has one
- **Countries (CH, NL, LU, AE, BE, DE, UK):** an ISO country code from the feed, or the country's city or country names
  in any location. A multi-location posting counts for every target country it lists. Pure "Remote" or
  region-only text ("EMEA", "MEA region") does not count. Look-alikes are excluded explicitly and tested:
  - Lake Zurich (IL), Amsterdam/Rotterdam (NY), Holland (MI)
  - the Belgian province of Luxembourg (Arlon, Bastogne, Marche-en-Famenne)
  - Kirchberg in Switzerland/Austria
  - "LU" as the Lucerne canton code, "BE" as Bern's, "DE" as Delaware
  - Brussels WI, Ghent NY, Berlin CT, Hanover NH, London ON, Cambridge MA. Any location string naming the
    USA, Canada or Australia never counts through a city name.
- **Category:** the title comes first, then the department, then the description. Specific categories are
  checked first:
  - `ecommerce_digital`: e-commerce, D2C, online/performance marketing, Amazon, Shopify
  - `marketing_analytics`: consumer insights, market research, marketing/sales analytics
  - `commercial`: trade/customer/shopper marketing, category management, key account, commercial excellence,
    customer development, field sales, SFE

  Then brand, business development, consulting, strategy, marketing, communications, sales, finance, HR,
  operations and other.
- **Exclusions and review:** engineering, IT, data science, lab, medical, legal and trades are excluded,
  including Dutch/German science compounds such as Microbiologie and Biochemie. Postings mixing business and
  technical terms, and generic Dutch "HBO/WO-stage" titles, go to `data/review.md`.
- **Duplicates:** postings identical in company, title and locations are merged into one.
- **Degree and languages:** read from the description, sentence by sentence and clause by clause (rules in
  `config.yaml` under `requirements`).
  - A language counts as *required* only with an explicit qualifier (fluent, fließend, courant, vloeiend, …).
  - It counts as *a plus* with plus, von Vorteil, un atout, een pré, ….
  - A bachelor's mention means *Bachelor OK*, unless the bachelor's is already completed and a master's is
    being pursued.
  - Without a description (most non-internship Workday postings) both stay unknown.
- **Descriptions:** feeds that include the text (Greenhouse, Lever, Ashby, Recruitee, Personio) are
  saved as they are. Where the list has no text, the finder uses the detail request it already makes for
  internship-like titles only (Workday, Oracle, Taleo, Eightfold, and the job pages of sitemap feeds), so no
  extra requests are made for other titles. Workday sitemap feeds have no description: their job pages are blocked.
- **Other countries:** add a block under `countries:` (codes, names, cities) and list it in `target_countries`.
  No code change is needed.

## Known limitations

- **Luxembourg and UAE coverage is thin.** Most of their large employers (banks, fund houses, FMCG regional HQs,
  Emirates, Majid Al Futtaim, Chalhoub, Alshaya) use SuccessFactors, Avature or in-house portals. They
  are listed per country in `gaps.md`. The big Dutch FMCG brands (Heineken, FrieslandCampina, Reckitt,
  PepsiCo, L'Oréal) are in the same situation; Henkel's careers site could not be read either.
- **Start dates are partial.** A start month is found for about 40% of open internships (2026-11 run), more
  where descriptions are fetched; the rest show a blank Start cell and score as "unclear". Duration is found
  for about half.
- **Coverage gaps.** Many big employers of business interns use systems without a readable public feed
  (SuccessFactors "classic" career sites whose robots.txt disallows bots, Avature, Abacus Umantis, in-house
  JavaScript portals), answer 403 to automated requests, or have careers sites that can't be analysed
  automatically. Examples: UBS, Pictet, the Big Four, the cantonal banks, and in Germany SAP, Mercedes-Benz,
  Bayer, Merck, E.ON, Metro, Lidl and Aldi Süd. They are listed in `gaps.md`, with the top 30 to check by hand. **SmartRecruiters**
  is supported in code but skipped, because `api.smartrecruiters.com/robots.txt` disallows all bots.
- **Workday details** (description, language, all locations) are fetched only for internship-like titles, to
  keep requests low. Other Swiss Workday postings show only the list summary (e.g. "3 Locations") and an
  approximate posted date.
- **Rules can misfire.** Category and language are keyword heuristics, so some postings will be
  mis-categorised. Check `data/review.md`, and tune `config.yaml` when a pattern repeats.
- **Fixed company list.** Only companies in `companies.yaml` are searched. A Swiss internship at an unlisted
  employer won't appear.

## Troubleshooting (without Claude)

Most problems show up as the issue **"Internship finder needs attention"**. Open it, then open the *Run log*
link and the red step.

| What you see | What it means | What you can do |
|---|---|---|
| Step **tests** failed | A recent change to `config.yaml` or the code broke a rule; the run stopped before fetching. | In the log, the failing test names the title or rule. Undo your last edit of `config.yaml` (*History* on github.com → revert), or adjust the rule until `python -m unittest discover -s tests -t .` passes locally. |
| Step **setup**/install failed, or a timeout | GitHub, PyPI or the runner had a temporary problem. | *Actions → the run → Re-run all jobs*. If it keeps failing for days, check githubstatus.com. |
| Step **publish** failed with `403` / `Permission … denied` | The workflow may not push. | *Settings → Actions → General → Workflow permissions → Read and write*, then re-run. |
| Step **publish** failed after 3 attempts | Someone pushed to `main` at the same moment three times. | Re-run the job. |
| **More than 10% of feeds failed** | Many feeds answered with errors at once: usually a temporary outage (e.g. Workday) or a rate limit (`HTTP 429`). | Wait for the next day's run; the issue closes itself if it recovers. If the same feeds keep failing, see the next row. |
| One company keeps failing (in the issue or in `data/last_run.json` → `failed`) | Its careers site moved to another system or tenant, or now blocks bots. | Open its `careers_url` (in `companies.yaml`). If it shows jobs, run `python -m finder discover "Name" <careers_url>`; if it finds a feed, re-add it with `--add --force`. Otherwise delete the company from `companies.yaml` (and add it to `gaps.yaml` if you like). |
| `robots.txt disallows` in an error | The site no longer allows automated access. | Remove the company. Don't work around it. |
| **Internships dropped by more than 40%** | One big employer's feed broke or changed format, or a `config.yaml` edit filters too much. | Compare `per_company` in `data/last_run.json` with the previous commit's version (GitHub *History*) to find the company that went to 0; then as in the row above. |
| The page shows old data | The run didn't commit (see the issue) or Pages is off. | Check the *Actions* tab; download the viewer from the latest run's artifacts. |
| Many Workday companies fail with HTTP 429 | Since 16 Nov 2026 Workday's sites refuse automated clients (Cloudflare bot filter). This is a block, not a bug; the finder does not work around it. | Their postings keep their last state and show **not updated since …** in the viewer; check those companies' careers pages by hand. 30 of them were moved to their own careers sites (sitemap + JSON-LD). The other 53 are read from the sitemap Workday itself publishes (named in each tenant's robots.txt; provider `workday_sitemap`): one request per site per run, no job pages fetched, because job pages are challenged too. It isn't a rate limit: at one request per 20 s only 2 of 12 pages came through. These postings have a title rebuilt from the URL (punctuation lost), the primary location and the link, but no description, posting date, pay, degree or start date; the sitemap lists only the newest jobs (often 100), so a posting stays listed for 30 days after it drops out. The old Workday entries are kept in companies.yaml with `disabled: true`, and the new entries say which feed they `replaces`, so the frozen Workday postings close by themselves after two runs. `workday` is listed under `health.known_blocked_providers` in config.yaml so the issue doesn't reopen daily. Remove it there if Workday feeds start working again. |
| A posting is in the wrong category or country | A keyword rule misfired. | Note the title. Category words are in `config.yaml` → `categories` / `excluded_*`; country rules under `countries` (`not_here`, `city_match_blockers`). Add the case to a test in `tests/`, then edit the rule. |
| Start date wrong or missing | The posting phrases it in a way `finder/dates.py` doesn't know. | Hover the Start cell to see the phrase used. Postings without a stated start show a blank cell and are never hidden by the April filter. |

To run anything locally: `pip install -r requirements.txt`, then `python -m finder run` (full run, about
15 minutes), `python -m finder verify` (check all feeds), or `python -m finder build` (rebuild the page only).

## Development

```bash
python -m unittest discover -s tests -t .   # classifier, location, category, store and resilience tests
python -m finder build                      # rebuild docs/index.html from data/jobs.json without fetching
```

Layout: `finder/http.py` (polite client), `finder/providers/` (one module per ATS), `finder/classify.py`,
`finder/store.py`, `finder/report.py`, `finder/viewer.py` + `viewer_template.html`, `finder/discover.py`,
`finder/pipeline.py`, `finder/__main__.py` (CLI). A failing feed is logged and skipped; it keeps its previous
data and never stops the run.
