# Public roster feasibility probe

Checked 2026-10-22. This is a small public-web-reader sample, not a live browser
capture or a working scheduled collector. Browser bootstrap failed because its
referenced browser-service.mjs component was missing. No client files were edited.

## Results

- FotMob Bayern team 9823: roster and player links readable. The reader labels
  the roster as crawled two months ago; current membership is not established.
- FotMob Kimmich 460632 / API-Football 502: DOB 1995-02-08 and Germany agree.
- FotMob Olise 1029063 / API-Football 19617: DOB 2001-12-12 and France agree.
- Both profiles expose preferred foot and position. Height is absent from the
  extracted field; the following number is a shirt number, not height.
- Sofascore Real Madrid 2829: reported 28 players and readable names, but the
  squad link returned the same document without individual player IDs. Rodrygo
  and Ferland Mendy are name-only candidates, not approved identity bindings.
- No new player identities or production fields were written. Four isolated
  samples are in artifacts/data/public_roster_probe_20261022.json.

## Source and operational boundary

https://www.fotmob.com/en-GB/teams/9823/squad/bayern-munchen/teams

https://www.fotmob.com/en-GB/players/460632/joshua-kimmich

https://www.fotmob.com/en-GB/players/1029063/michael-olise

https://www.sofascore.com/football/team/real-madrid/2829

FotMob explicitly disallows systematic/regular automatic use in the page footer.
Do not promote this feasibility sample into a scheduled scraper without a suitable
permission route. Sofascore's readable page is not proof of API availability or
reuse permission. No rate limit, sign-in or anti-bot mechanism was bypassed.

Recommendation: these samples support selective cross-checking, not deployment
of a new production feed. Preserve provider IDs separately, require multiple
identity attributes, and keep historical observations distinct from current
roster claims. Continue the quota-aware existing provider path for bulk ingestion.
