# Three-device evidence review — November 3, 2026

Prepared corrections only. Generated files are unchanged. Merge does not publish
data; the guarded update workflow must subsequently run under the normal release
process. No WordPress or CDN delivery was triggered during this review.

| Device | Reviewed release | Support representation | Evidence |
|---|---|---|---|
| Galaxy S24 | 2024-01-31 | January 2031 minimum window; month precision | [Samsung US launch policy](https://news.samsung.com/us/enter-new-era-of-mobile-ai-samsung-galaxy-s24-series/) |
| Galaxy S25 | 2025-02-07 | 2032-01-31 published endpoint, day precision | [US SM-S931ULGEXAA specification](https://www.samsung.com/us/smartphones/galaxy-s/galaxy-s25-mint-256gb-sm-s931ulgexaa/), [US launch and availability](https://news.samsung.com/us/samsung-galaxy-s25-series-sets-standard-of-ai-phone-true-ai-companion-unpacked2025/) |
| Pixel 8 | 2023-10-12 | October 2030 minimum window unchanged | [Google retail availability](https://blog.google/products-and-platforms/devices/pixel/google-pixel-8-pro/), [update policy](https://support.google.com/pixelphone/answer/4457705), [availability month](https://support.google.com/pixelphone/answer/15738422) |

Samsung's S25 US HTML was retrieved directly and includes “Security Update Period
(Valid until)” with “31 January 2032”. The web reader timed out on this URL;
the direct HTTPS fetch returned 200 and the specification. Do not replace this
explicit date with February 7, 2032 calculated from retail availability.

S24's US announcement gives seven years and January availability, not an exact
final patch day. The UK Enterprise Edition specification is not substituted for
the US policy. Its old legacy `eol` remains for compatibility; the reviewed
`support_window` controls status and display. Samsung's current security scope
listed S24 among monthly models on the review date.

Pixel 8 was announced October 4 but became available October 12. Its reviewed
audit release field and the Pixel 8/S24 canaries change together with the explicit
overrides. Canary enforcement remains active; no validation gate is disabled.
Other family variants are outside this three-record review and need their own
follow-up. The Pixel support evidence retains its original September review date;
this release correction does not pretend all 38 Pixel records were newly audited.

Validation: 55 offline tests; the new test checks exactly three record changes,
unchanged IDs/count and month/day boundaries. The live upstream dry run passes
with 139 records, zero additions and one legacy EOL change (S25). Generated
JSON is never hand-edited. `generate_static.py` now explicitly reads UTF-8 to
preserve source qualifications when the generator runs on Windows.

Consumer preparation is on private `androidguide-notes` branch
`codex/device-source-evidence`: three evidence sections and four synchronized
page snapshots. Those snapshots are a local preview against the November 1
baseline, not a publication. After data publication, regenerate them from the
actual published files and review that final diff before WordPress deployment.
