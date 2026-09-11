# Google Pixel support-date evidence audit

Audit date: 2026-09-11  
Dataset snapshot: 2026-09-01 (`138` devices; `38` Google Pixel records)  
Status: evidence classification only. No generated data or publishing behavior changed.

## Result

All 38 Pixel records were matched by model name against Google's current update-policy
and Google Store US availability pages.

- **24 current-policy records:** Google supports a year-month minimum guarantee, not an
  exact final day. These become `precision: month`, `basis: policy_calculation`, and
  `meaning: minimum_guarantee`.
- **14 historical records (Pixel 5a and earlier):** Google's current policy page confirms
  that they no longer receive Android version or security updates, but it no longer gives
  their historical cutoff dates. Their exact-looking upstream `eol` days remain raw
  aggregator estimates pending archived primary evidence. They do not become Google dates.
- **0 Pixel records have manufacturer-supported day precision in the sources reviewed.**

The machine-readable inventory is `pixel-support-audit.json`. Its coverage test fails if
the Pixel IDs in `devices.json` and the audit ever diverge.

## Sources and what each proves

1. [Current Pixel update policy](https://support.google.com/pixelphone/answer/4457705)
   names the phones covered by five- and seven-year policies and says Pixel 5a and earlier
   no longer receive OS or security updates.
2. [Google Store US availability months](https://support.google.com/pixelphone/answer/15738422)
   supplies the month from which those durations run. It publishes months, not exact days.
3. [Google's Pixel 6 launch announcement](https://blog.google/products-and-platforms/devices/pixel/meet-pixel-6-pixel-6-pro/)
   corroborates at least five years of security updates and October 28, 2021 US availability.
4. [Google Pixel Support Team's November 2023 update announcement](https://support.google.com/pixelphone/thread/242705137/google-pixel-update-november-2023?hl=en)
   includes Pixel 5. This establishes an observed November update, while the current policy
   page establishes only that Pixel 5 is no longer supported. It does not turn November 5
   into a promised cutoff. The announcement is corroboration, not the primary policy source.
5. [August 2024 Pixel bulletin](https://source.android.com/docs/security/bulletin/pixel/2024-08-01)
   and Google's August rollout identify an August security update for Pixel 5a. A delivered
   patch still does not establish an exact manufacturer-promised cutoff day.

## Current-policy records: month precision

| Device IDs | US availability | Policy | Supported guarantee value | Raw upstream values |
|---|---:|---:|---:|---:|
| `google-pixel-11`, `-11-pro`, `-11-pro-xl`, `-11-pro-fold` | 2026-08 | 7 years | 2033-08 | 2033-08-01 |
| `google-pixel-10a` | 2026-03 | 7 years | 2033-03 | 2033-03-01 |
| `google-pixel-10-pro-fold` | 2025-10 | 7 years | 2032-10 | 2032-10-01 |
| `google-pixel-10`, `-10-pro`, `-10-pro-xl` | 2025-08 | 7 years | 2032-08 | 2032-08-01 |
| `google-pixel-9a` | 2025-04 | 7 years | 2032-04 | 2032-04-01 |
| `google-pixel-9-pro`, `-9-pro-fold` | 2024-09 | 7 years | 2031-09 | 2031-09-01 |
| `google-pixel-9`, `-9-pro-xl` | 2024-08 | 7 years | 2031-08 | 2031-08-01 |
| `google-pixel-8a` | 2024-05 | 7 years | 2031-05 | 2031-05-01 |
| `google-pixel-8`, `-8-pro` | 2023-10 | 7 years | 2030-10 | 2030-10-01 |
| `google-pixel-fold` | 2023-06 | 5 years | 2028-06 | 2028-06-01 |
| `google-pixel-7a` | 2023-05 | 5 years | 2028-05 | 2028-05-01 |
| `google-pixel-7`, `-7-pro` | 2022-10 | 5 years | 2027-10 | 2027-10-01 |
| `google-pixel-6a` | 2022-07 | 5 years | 2027-07 | 2027-07-01 |
| `google-pixel-6`, `-6-pro` | 2021-10 | 5 years | 2026-10 | 2026-10-01 |

For every row above, the upstream day `01` falls in the correct policy month but is not
promoted to an exact Google endpoint.

## Historical records: status known, cutoff day not established

| Device IDs | Google Store US availability | Raw upstream `eol` | Audit classification |
|---|---:|---:|---|
| `google-pixel-5a` | 2021-08 | 2024-08-01 | no longer receives updates; exact cutoff unverified |
| `google-pixel-4a-5g` | 2020-10 | 2023-11-05 | no longer receives updates; exact cutoff unverified |
| `google-pixel-5` | 2020-10 | 2023-11-05 | no longer receives updates; exact meaning of raw date is not established |
| `google-pixel-4a` | 2020-08 | 2023-08-05 | no longer receives updates; exact cutoff unverified |
| `google-pixel-4`, `-4-xl` | 2019-10 | 2022-10-05 | no longer receives updates; exact cutoff unverified |
| `google-pixel-3a`, `-3a-xl` | 2019-05 | 2022-05-05 | no longer receives updates; exact cutoff unverified |
| `google-pixel-3`, `-3-xl` | 2018-10 | 2021-10-05 | no longer receives updates; exact cutoff unverified |
| `google-pixel-2`, `-2-xl` | 2017-10 | 2020-10-05 | no longer receives updates; exact cutoff unverified |
| `google-pixel`, `-pixel-xl` | 2016-10 | 2019-10-06 | no longer receives updates; exact cutoff unverified |

The Pixel 4a (5G) also exposes a source conflict that must not be silently recomputed:
the dataset release date is 2020-11-05, while Google's current US availability table says
October 2020. The current Google evidence supports the device's ended status but supplies
neither the historical duration nor a replacement exact date.

## Required consumer behavior

For the Pixel 6 and 6 Pro during October 2026:

- status: **The guaranteed support window ends this month.**
- date: **October 2026 — exact end date not specified.**
- no exact-day countdown.

From November 1, 2026:

- status: **The stated guarantee period has elapsed.**
- do not say Google definitely stopped patches on November 1.

For historical Pixels, consumers may say Google currently lists the model as no longer
receiving updates. They may not attribute the raw upstream day to Google.

## Contract refinement found by the audit

`support_window` and `support_observation` must be siblings. A minimum guarantee, an
observed update, and a current no-longer-supported status answer different questions and
can coexist. The contract validator now enforces separate observation status, observation
date and provenance. This is still not connected to `update_devices.py`.

## Out of scope

- No `devices.json`, override, workflow, static page or WordPress file was changed.
- No production pipeline was run.
- Archived historical Google tables can improve the 14 old records later, but lack of an
  archive does not justify treating their exact-looking aggregator days as manufacturer facts.
