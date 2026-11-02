# Interpretation

The scan summary v2 has one decision source: `assessment`. Start with its headline and
recommendation. It separates `conclusions` (verdict/action pairs), `user_actions` (justified
configuration checks) and `tool_gaps` (unfinished measurement). Raw baseline findings and
generic motivation paragraphs remain in the local audit report, not in this model summary.
`incomplete` means the measurement is unfinished; `attention` means a specific discrepancy,
source label, score or report needs checking; `measured` means readings are available. None
of these states represents account approval.

IPQS scores use the provider's documented thresholds: 75+ suspicious and 90+ high risk,
attributed to IPQS, not 上游服务商. Below 75 means below that threshold, not universally safe.
Source: https://www.ipqualityscore.com/documentation/proxy-detection-api/response-parameters
(fraud_score definition, checked 2026-10-19). Other providers retain their own semantics;
network abuse ratios are never assigned to an individual IP.

| Assessment | Meaning |
| --- | --- |
| needs_action | A concrete preparation task applies, such as finding the requested client on PATH. |
| needs_confirmation | A difference, scope or policy question needs user/source confirmation. |
| verified | A specific observation or declared expectation is established within its scope. |
| not_applicable | The selected scenario does not need this item. |
| unknown | Evidence is missing, stale, failed, not comparable, or outside the observable boundary. |

Coverage measures acquisition only. Complete coverage is not a score of account safety.
The default offline run leaves optional external checks unknown.

The browser probe uses no external requests on open or on a local-only run. If enabled,
it contacts ipify without credentials or referrer. The CLI's route can follow system/environment
HTTP proxy settings; it does not emulate a browser. IPWhois adds the queried IP as an external
data boundary. Neither service's label is 上游服务商's internal classification.

These assessments describe the baseline report. Enhanced findings use `observed` for a returned
measurement, `review` for a difference/tag that needs context, and `unknown` for insufficient evidence.
Provider execution states (`missing_key`, `quota_exceeded`, `timeout`, `partial`, etc.) describe
measurement coverage, never the account's safety. Keep original score scopes and scales separate.
Unselected or unconfigured IPQS, AbuseIPDB and ipapi.is belong under optional enhancements, not tool gaps
or mandatory user actions. Their absence does not invalidate an otherwise completed no-key check.
Selected enhancement failures and missing response fields remain visible with their original execution status.

The enhanced model summary excludes provider free text, IPs, country codes and browser attributes.
It retains scoped timestamps, selected numerical findings and fixed interpretation text.
Use the packaged rule explanation for source interpretation. Do not read the private snapshot
just to make the response more detailed.

`dns` is a separate, optional observation of the default resolver used by `dig`. It is not a browser
DNS test. A resolver's public address need not match an HTTPS egress address. ECS is a reported subnet,
not an account identifier; a cache hit does not establish a fresh authoritative observation.
