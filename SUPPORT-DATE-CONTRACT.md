# Support-date precision contract

Status: proposed schema contract and executable validation tests. Not connected to
the publishing pipeline. Merging or deploying it alone must not change
`devices.json` or AndroidGuides.com.

## Problem

The existing schema stores every security-support value in an ISO `eol` day.
That shape cannot distinguish an exact manufacturer date from a published month,
a policy calculation, a third-party estimate or an observed removal from a
support list. Consumers consequently turn month-level evidence into exact-day
claims.

For example, Google's Pixel policy and US availability information support an
October 2026 minimum-commitment window for Pixel 6. They do not certify either
October 1 or October 31 as the final patch day. The current upstream value
`2026-10-01` must therefore remain visible as a raw input, not become a claimed
manufacturer endpoint.

## Backward-compatible record shape

Schema `1.1` retains the six existing fields. `source` remains exactly
`endoflife.date | override`. `eol` remains temporarily as a legacy sorting and
compatibility field, but it is not authoritative for display or status whenever
`support_window` exists.

```json
{
  "id": "google-pixel-6",
  "brand": "Google",
  "model": "Pixel 6",
  "released": "2021-10-28",
  "eol": "2026-10-01",
  "source": "endoflife.date",
  "support_window": {
    "published_value": "2026-10",
    "precision": "month",
    "basis": "policy_calculation",
    "meaning": "minimum_guarantee",
    "raw_upstream_value": "2026-10-01",
    "provenance": {
      "source_url": "https://support.google.com/pixelphone/answer/4457705",
      "checked_on": "2026-09-11",
      "market": "US",
      "model_codes": [],
      "note": "Derived from Google's minimum-support policy and US availability month; no exact final patch day is published."
    }
  }
}
```

Month records intentionally contain no derived first-day or last-day bound.
Consumers compare the `YYYY-MM` value as a calendar month. This prevents a
derived October 31 from being mistaken for a manufacturer-certified endpoint.

## Controlled vocabularies

`precision`:

- `day` — the cited evidence publishes an exact calendar day.
- `month` — the evidence supports a named year-month but no exact day.
- `unknown` — the available evidence cannot support even a dated period.
  `published_value` must be null; consumers show an unavailable/uncertain status.

`basis` describes how the window was obtained:

- `manufacturer_published`
- `policy_calculation`
- `observed_scope_removal`
- `aggregator`

`meaning` describes what the evidence actually asserts:

- `minimum_guarantee`
- `scheduled_endpoint`
- `up_to`
- `estimate`
- `observed_removal`

Basis and meaning are separate. A policy calculation can produce a minimum
guarantee without establishing an observed stop. Removal from a live support
scope is an observation, not proof of the last delivered patch.

## Consumer rule

No consumer may render `eol` directly once `support_window` exists.

For a month-precision minimum guarantee:

- During the named month: “The guaranteed support window ends this month.”
- From the next month: “The stated guarantee period has elapsed.”
- Date display: “October 2026 — exact end date not specified.”
- Never display an exact-day countdown or claim that patches definitely stopped
  on the first of the following month.

For day precision, Task J's existing rule remains: the published date is the
final supported calendar day and status changes the following day, subject to
the record's stated meaning and market/model applicability.

All consumers migrate together: pipeline sentence generation, P4 facts/status/
FAQ/JSON-LD, homepage checker and fallback, directory table/static/fallback,
timeline, longest-supported, losing-updates, SEO descriptions and explanatory
metadata.

## Validation and rollout gates

The executable contract in `support_contract.py` and
`test_support_contract.py` requires:

1. Complete provenance with HTTPS source, checked date, market, model-code list
   and note.
2. Day values to be exact ISO dates.
3. Month values to use `YYYY-MM` with no synthetic day-shaped bound.
4. Unknown precision to carry no synthetic published value.
5. Basis/meaning combinations to be semantically compatible.
6. Existing `source` vocabulary to remain unchanged.
7. `exact_end_date()` to return a day only for `day` precision.

Before schema `1.1` can be emitted:

- Audit all 38 current Pixel records; do not infer precision solely from brand
  or a day-of-month value.
- Resolve A37's source/market conflict and retain A23's UK SKU qualification.
- Update every first-party consumer in the same reviewed release.
- Run the existing count, schema, canary and static-generation tests plus new
  cross-consumer day/month/unknown boundary fixtures.
- Do not run the production workflow until both repositories are merged and the
  WordPress deployment artifacts are ready.
