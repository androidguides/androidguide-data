# PIPELINE OPS — Guarded Pipeline (P1) + Tiered Serving (P3)
*Updated 2026-08-04.*

How the AndroidGuides.com data pipeline protects itself, serves data in tiers,
how to correct bad data, and how to roll back. Written for Matt (non-developer,
GitHub web UI only).

> **What changed 2026-08-04:** the WordPress push now **retries transient
> failures** (see "The WordPress push"), the CDN purge **verifies itself**, and
> there is a new section on what to do **if endoflife.date ever disappears**.

## What runs each month

On the 1st ~12:00 UTC (or on demand: Actions → Update device database → Run
workflow), `update-devices.yml` does, in order:

1. Fetch fresh data from endoflife.date.
2. Merge `overrides.json` LAST — your manual corrections always win.
3. Run validation gates:
   - device count ≥ 100 and ≤ 500
   - count moved no more than ±10% vs the current devices.json
   - every record has all 6 fields, valid ISO dates, eol after released, no duplicate ids
   - brand floors: ≥ 15 Google, ≥ 40 Samsung
   - 4 canary devices exist with their known release dates
     (google-pixel-8, google-pixel-6, samsung-galaxy-s24, samsung-galaxy-z-fold5)
4. ANY gate fails → devices.json is NOT written, the run fails, **GitHub emails
   you**, and the previous good data stays live. Bad data cannot reach visitors.
5. Gates pass → regenerate `devices-static.html` (the crawlable sentences).
6. Commit devices.json + devices-static.html.
7. **Purge the jsDelivr CDN, then read the CDN back and confirm** its `generated`
   date matches the repo, retrying to beat propagation lag. (Before this was
   added the purge fired too early, jsDelivr re-cached the OLD file, and the step
   reported a fake "OK" — the CDN sat 18 days stale while everything looked green.)
8. **Push both files to WordPress** (same-origin fallback, see below), with retries.

A second workflow, **Data staleness check**, runs every Monday and fails
(= emails you) if repo data is over 40 days old (pipe silently dead), the
jsDelivr CDN copy lags the repo by over 7 days, or the CDN is unreachable.

Silence = healthy. Email = something needs a look. Nothing auto-fixes itself —
a smoke detector, not a sprinkler.

> One-time check: github.com → Settings → Notifications → Actions →
> make sure "Email" is ticked for failed workflows.

> **Staleness-check caveat:** its comparison logic is correct, but a single
> passive read of jsDelivr can hit a fresh edge node while visitors hit a stale
> one (and the read itself warms that edge). That is why it false-greened once
> while the CDN was badly stale. The self-verifying purge in step 7 is now the
> primary defense; the weekly age-check (dead-pipe detection) is still solid.

> **⚠ Do not run the workflow manually more than once a day.** Several manual
> runs in a row trigger SiteGround's firewall against the GitHub runner, which is
> what broke the push on 2026-08-01. One run, then wait.

## How visitors get data (tiered serving, P3)

`/devices` loads the device list in this order, stopping at the first that works:

1. **CDN** — `https://cdn.jsdelivr.net/gh/androidguides/androidguide-data@main/devices.json`
2. **Same-origin** — `https://androidguides.com/wp-content/uploads/androidguide/devices.json`
   (pushed by the pipe every run; step 8 above)
3. **Embedded snapshot** — a 130-device copy baked into the /devices page itself,
   used only if both the CDN and the server are unreachable.

Each shows a "Data as of <date>" label so a visitor always knows how fresh the
answer is. The same-origin copy also carries `devices-static.html`.

> **The same-origin copy matters more than its "fallback" name suggests.** The
> per-device pages at `/device/<slug>/` and `/device-sitemap.xml` read that file
> off local disk. If the push fails repeatedly, all 130 device pages quietly
> serve stale data while the CDN looks perfectly healthy. Treat a red push step
> as a real problem, not a cosmetic one.

## The WordPress push (P3) — how it works and how to fix it

- The pipe authenticates to WordPress with an **application password** (created
  in Users → Profile → Application Passwords, named `androidguide-pipe`), stored
  ONLY as GitHub Actions secrets `WP_APP_USER` and `WP_APP_PASSWORD`. Never in
  the repo.
- It POSTs to a small endpoint registered by a WPCode PHP snippet
  ("AndroidGuides push endpoint"): `POST /wp-json/androidguide/v1/push`. The
  endpoint only accepts the two known filenames and only an admin can call it.
- **Retries (added 2026-08-04).** Each file gets up to `PUSH_ATTEMPTS = 3`
  attempts, `RETRY_WAIT = 60` seconds apart.
  - **Retried:** a non-JSON response (SiteGround's `sgcaptcha` challenge page),
    HTTP 5xx, HTTP 429, network/timeout errors.
  - **NOT retried:** HTTP 4xx such as bad auth or a rejected filename — those
    fail immediately instead of wasting two minutes on a problem that will not
    fix itself.
  - A retry that works logs `succeeded on attempt N`. Persistent failure still
    exits non-zero → red run → email. The retry absorbs transient noise without
    ever hiding a real fault.
- **If the "Push same-origin copy to WordPress" step goes red, check in this order:**
  1. **Read the log.** `not JSON (firewall challenge?)` on all three attempts =
     SiteGround's firewall, not your credentials. Usually caused by several
     manual runs in a row. Wait a few hours and run once.
  2. **HTTP 401/403** = the application password. Regenerate it (Users → Profile
     → Application Passwords → delete old, add new `androidguide-pipe`) and
     update the `WP_APP_PASSWORD` secret (repo → Settings → Secrets and
     variables → Actions). Nothing else changes.
  3. Either way the CDN path keeps working, so visitors are fine while you fix
     it — but the device pages are staling, so do not leave it.
- **Verify the fix from outside:**
  `https://androidguides.com/wp-content/uploads/androidguide/devices.json?cb=1`
  should show today's `generated` date. **The `?cb=1` is required** — see the
  gotcha below.

## ⚠ Verifying anything on androidguides.com from outside

SiteGround's bot filter returns **empty, stale, or degraded responses to
non-browser clients on bare URLs** (no query string). This is not theoretical —
on 2026-08-04 it produced a full false alarm: an audit reported `/about` as
`noindex, nofollow` when the live page was perfectly healthy, and both
`/contact` and `devices.json` returned *empty* on bare URLs while returning
correctly with `?cb=`.

**Rules:**
- Always append a cache-busting query string (`?cb=1`) when fetching any URL on
  this domain with a script, a fetch tool, or curl.
- A tool-reported `noindex` on this site **is not evidence**. Confirm with Google
  Search Console → URL Inspection → **TEST LIVE URL**, which fetches as Googlebot
  from Google's own IPs and bypasses both caching and the bot filter.
- A browser in incognito is ground truth for anything JavaScript-driven.
- `push_to_wp.py` sends a browser User-Agent for this same reason — keep that if
  you ever rewrite it.

## Correcting a wrong date (overrides.json)

Never edit devices.json — the next run overwrites it. Instead edit
`overrides.json` on the GitHub website (pencil icon), add an entry inside the
`"overrides": [ ]` list, and commit. It applies on the next run (or trigger one:
Actions → Update device database → Run workflow).

**Fix a wrong EOL date:**
```json
{
  "id": "samsung-galaxy-s22",
  "fields": { "eol": "2027-06-30" },
  "security_eol_basis": "manufacturer_exact",
  "source_url": "https://www.samsung.com/example/security-spec/",
  "source_note": "Samsung publishes 30 June 2027 as the security-update deadline.",
  "reason": "Samsung security page shows June 2027, endoflife.date lags",
  "added": "2026-07-26"
}
```

**Add a device the source is missing:**
```json
{
  "id": "samsung-galaxy-a99",
  "add": true,
  "fields": {
    "brand": "Samsung", "model": "Galaxy A99",
    "released": "2026-06-01", "eol": "2032-06-01"
  },
  "security_eol_basis": "manufacturer_exact",
  "source_url": "https://www.samsung.com/example/security-spec/",
  "source_note": "Samsung publishes 1 June 2032 as the security-update deadline.",
  "reason": "Missing upstream; dates from samsung.com press release",
  "added": "2026-07-26"
}
```

**Remove a device that shouldn't be listed:**
```json
{
  "id": "samsung-galaxy-a13-sm-a137",
  "remove": true,
  "reason": "Regional variant, confusing US visitors",
  "added": "2026-07-26"
}
```

Rules: `id` and `reason` are required (a missing reason skips the entry). Multiple
entries are separated by commas. Overridden/added records get `"source":
"override"` so human facts stay distinguishable from automated ones. Overrides
are validated too — a typo'd date trips the gate and emails you rather than
shipping. To clear a missing-security-date provenance failure, the override for
that exact device id must either be an explicit `"remove": true` exclusion or
provide all of `fields.eol`, a reviewed `security_eol_basis`, an HTTPS `source_url`,
and a non-empty `source_note`. `manufacturer_exact` means the manufacturer publishes
the full date. `manufacturer_month_end` means the manufacturer
publishes only an end month; `fields.eol` must normalize that month to its final calendar
day and `source_note` must state the normalization explicitly. These are override metadata,
not values of the generated record's `source` field: generated records remain either
`"endoflife.date"` or `"override"`. An unrelated override never clears another device's
failure.

## Security-date provenance guard

The endoflife.date API exposes Android-upgrade support separately from security-update
end dates. The pipeline accepts only a dated upstream `eol` as a security-update end;
it never substitutes the API's `support` field. A record with a support date but no
explicit security end trips the validation gate and stops the entire publication. The
previous dataset keeps serving until the security date is published, a manufacturer-backed
override is reviewed, or the provenance-aware schema and renderers are deployed together.
When a manufacturer-backed override is used, its source and reasoning remain auditable in
`overrides.json`; the pipeline never treats the API's `support` value itself as evidence.

Samsung dates reflect endoflife.date's explicit security-update end where published.
Records without an explicit security end should be treated as unknown and verified with
Samsung. This semantic guard matters because a plausible date of the wrong kind passes
ordinary schema, range, and count validation.

## If endoflife.date is down, rate-limits us, or disappears

The entire database derives from one upstream source. This is the single biggest
structural risk, and it grows every time device coverage grows.

**What already protects you, automatically:**

- A failed or empty fetch **trips the validation gates**, so `devices.json` is
  not written. The last-good data stays live and the site keeps serving correct
  answers indefinitely. **The site does not go dark.**
- The run goes red and GitHub emails you, so you find out.
- `overrides.json` is merged **last**, so anything declared there beats upstream.

**What that means in practice:**

- *Source is down for a few days:* do nothing. Last-good data serves. Ignore the
  red run once you have confirmed that is the cause.
- *Source is wrong about specific devices:* add override entries. Normal
  operation.
- *Source is gone for good:* `overrides.json` can carry records outright via
  `"add": true`. Maintain the changed devices by hand (few devices change in any
  given month) while a replacement source is arranged. Verify against
  manufacturer pages — Samsung's update-scope page and Google's Pixel support
  timelines, both already cited on /contact.

**⚠ This fallback has never been exercised.** Recommended one-time drill: pick a
single device, add an override with a deliberately distinctive date, run the
pipe, confirm the override wins on the live site, then revert. A fallback nobody
has run is a hope, not a plan. Do this before expanding device coverage.

**Still worth building:** a periodic off-repo backup of the last-good
`devices.json`, so data survives even if the repo and the source are both
unavailable.

## Rollback ritual (bad data got committed anyway)

1. Repo → `devices.json` → **History** (clock icon) → click the last GOOD commit.
2. Click **Raw**, select all, copy.
3. Back on `main`: `devices.json` → pencil → select all → paste → commit
   `Rollback to <date> data`.
4. Force the CDN to pick it up now: open
   `https://purge.jsdelivr.net/gh/androidguides/androidguide-data@main/devices.json`
   in your browser (a page of JSON = success). To read the current CDN copy in a
   browser without its cache, add `?cb=1` to the devices.json URL.
5. Trigger the workflow once (Actions → Run workflow) so the same-origin copy and
   the crawlable fragment also refresh to the good data.
6. Click **Purge SG Cache** in the WordPress admin bar so the cached device pages
   pick up the corrected data.
7. Fix the root cause via overrides.json so the next run doesn't recommit the bad
   data (the gates should catch it, but don't rely on luck).

## Monthly rhythm

- **1st of the month ~12:00 UTC:** pipe runs. No email = success.
- **Then click Purge SG Cache** in the WordPress admin bar, once. The device
  pages are full-page cached and will not show fresh data until you do. The CDN
  and same-origin copies refresh on their own.
- **Any Monday email from "Data staleness check"** = investigate that day.
- **Canary trip after an endoflife.date format change:** check their site; if the
  new value is actually correct, update the CANARIES dict in update_devices.py.
- **Occasional re-paste of point-in-time content.** The pipe keeps the CDN and
  same-origin copies current automatically, but these are snapshots frozen at
  paste time and need a manual refresh when the device list changes materially:
  - `/devices` — the `#agd-static` crawlable section and the embedded snapshot
  - the homepage — its embedded fallback device list and static device count
  - `/longest-supported-phones`, `/timeline`, `/phones-losing-updates-2026` —
    fully static by design
- **Hand-maintained date moves** on `/phones-losing-updates-2026` and `/timeline`:
  after **2026-08-27** move Galaxy Z Fold3 / Z Flip3 to "already ended"; after
  **2026-10-01** move Pixel 6 / 6 Pro. ~30 seconds each.
