# fineview-planning-leads

Daily automation that finds approved planning applications within ~10 miles of Radlett likely to need >£5k of windows/doors, and turns them into leads for Fine View Windows.

## Pipeline
1. **Scrape** Idox Public Access portals (`config/councils.yaml`) for applications decided in the last 3 days.
2. **Filter** to approved, large jobs (`src/filters.py`) and score High/Med.
3. **Categorise** each party: Developer / Builder / Architect-agent / Homeowner.
4. **Enrich businesses only** (Companies House, website, email, phone, socials).
5. **Homeowners** are stored with the property address only and queued for a consent-first letter (QR + phone opt-in).
6. Everything lands in **Supabase** (`supabase/schema.sql`) — the CRM foundation.

## Setup
1. Run `supabase/schema.sql` in your Supabase project's SQL editor.
2. Add repo secrets (Settings → Secrets and variables → Actions):
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
   - `COMPANIES_HOUSE_API_KEY` (free: developer.company-information.service.gov.uk)
   - `SERPAPI_KEY` (optional, finds company websites)
3. Actions → *Daily planning scrape* → **Run workflow** to test. It then runs daily at 06:17 UTC.

## Roadmap
- [ ] Verify/adapt St Albans, Welwyn Hatfield, Harrow portals
- [ ] Business email sequence (with one-click unsubscribe + suppression)
- [ ] Stannp letter sending + QR opt-in landing page
- [ ] CRM front end
