# The Daily Brief

A personal news and research page that rebuilds itself every morning.
No social media, no proxies, no server to maintain.

- **World / El Mundo**: official RSS feeds from Reuters, AP, BBC, Guardian, NYT, NPR,
  El País, BBC Mundo, DW, France 24, El Mundo, Clarín (last 30 hours).
- **The Bench**: PubMed, last 7 days, for NAD+/mitochondria, AAA, DVT, carotid injury,
  vein graft / jugular transplant, PAD2 & TBI. Papers added today are flagged.
- **Sign-out**: PubMed for GI, GYN and general diagnostic pathology journals.
- **Past editions**: the last 60 days are kept.

## One-time setup (about 10 minutes)

1. Create a free account at github.com if you don't have one.
2. Create a new **public** repository, e.g. `daily-brief`.
   (Free GitHub Pages needs a public repo. The page only contains headlines and
   paper titles, and it asks search engines not to index it.)
3. Upload everything in this folder, **including the hidden `.github` folder**.
   The easiest way: on the repo page choose "uploading an existing file" and drag
   the whole folder in, or use `git push` from your computer.
4. Settings → Actions → General → Workflow permissions → choose
   **Read and write permissions** → Save.
5. Settings → Secrets and variables → Actions → New repository secret:
   `NCBI_EMAIL` = your email (NCBI asks for a contact address).
   Optional: `NCBI_API_KEY` from your NCBI account for faster PubMed access.
6. Actions tab → "Build daily brief" → **Run workflow**. Wait about 1 minute.
7. Settings → Pages → Source: **Deploy from a branch**, Branch: `main`, folder: `/docs` → Save.
   Your page appears at `https://<your-username>.github.io/daily-brief/` within a minute or two.

After that it rebuilds by itself every day at 11:00 UTC (6 am Chicago in summer,
5 am in winter). Use "Run workflow" any time you want an extra refresh.

## Changing things

Edit `config.json` on GitHub:
- add or remove news sources (any RSS or Atom feed URL), and change how many stories each shows
- edit the PubMed queries (same syntax as the PubMed search box)
- change `research_window_days` or `news_window_hours`

## If something breaks

- A single outlet that changes its feed shows "Feed unavailable today" on the page;
  everything else still builds. Swap the URL in `config.json`.
- If every source fails, the build stops and yesterday's page stays up.
- GitHub pauses scheduled workflows in repos with no activity for 60 days;
  the daily commit counts as activity, so this normally never happens.
  If it does, press "Enable workflow" in the Actions tab.
