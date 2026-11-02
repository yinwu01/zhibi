# Detection mode

Use `python3 <skill>/scripts/zhibi.py` for every command here. The release includes the runtime.

## Select the subject and scope

- Reuse the task, channel, phase and route expectation. Establish whether the agent is local, remote or in a container.
- Run `doctor`; use `capabilities` only if installed command support is unclear. `scan` produces a local report without network access by default.
- For an IP reputation check, use `scan --network --reputation --progress`. Add `--ipv6` when relevant.
  This no-key preset selects IPWhois, ProxyCheck v3, IPQuery and StopForumSpam. It returns
  attribution, proxy labels, native risk scores and a scoped spam-history lookup. Do not
  substitute anonymous ipapi.is, which now returns identity only, for these reputation sources.
  These requests reveal request and queried IPs to the named services. Explain that scope; use existing authorization.
- Only when the user chooses enhanced data, add their selected providers: `--provider ipqs`, `--provider abuseipdb` or keyed `ipapi`. Existing keys alone do not opt the user into extra recipients.
  Complete the default check first. Unselected or unconfigured optional providers are not failed baseline checks,
  do not become user action items, and do not require all three registrations. Link [optional setup](providers.md) if requested.
  `providers` reads keys inside the local core and shows only configured status to the model. See [provider coverage](providers.md).
- The same `scan` options plus `--dry-run` show recipients, fields, fixed parameters and request limits.
  Missing keys, quotas and unavailable fields remain explicit. Do not silently switch providers or scrape checker websites.

## Actual browser measurement

For 目标服务 web registration, the agent's route alone is insufficient:

1. Prefer `session --preset basic --network --out <new-run-directory>`; use `--preset all` only for an authorized complete check.
2. Open the returned one-time localhost URL in the actual browser/profile, use computer use to click **开始检查**, wait for completion, then click **保存到本机并生成报告**. The receiver accepts only same-origin POST, stops after one save and never serves private reports.
3. If loopback is unreachable in this profile, use `session --file`: open its local HTML and save the output. Only the current random file in Downloads or the specified import path is read.
4. The core imports browser values privately and runs `suite` automatically. Read its curated summary, then show the local report.

File fallback remains available: `browser --advanced --out <new-local-file.html>`, save the browser JSON, then `suite --browser <local-json> --target browser --preset basic --network`. See [all optional tools](optional-tools.md).

Pass the file path to the script; do not read its raw JSON into model context. It contains IPs and browser metadata.
Old, future-dated, automated or failed browser measurements cannot supply a user browser IP for enrichment.
Browser IPv6 enrichment also requires `--ipv6`. A failed family is not replaced with another family.
WebRTC uses the browser and selected Google STUN service, without camera/microphone access.
Different protocols may use different routes. No candidates or a timeout is not proof of no leak.

The same advanced page includes six independently optional local checks under “加做浏览器深入检查”:
UTC offset/language variants, browser/version/device hints, runtime markers, browser-visible logical CPU count,
26 fixed font candidates, and the probe page's geolocation permission state. These need no Key or external service.
Use them when relevant to the user's scope; leave them unchecked for a basic IP check.
Save and import the same JSON file; v4 includes the selected details and extensions, while v1/v2/v3 imports remain supported.
The core validates private values, renders them in the local report, and exports only per-check states to the Agent.
Do not read the raw export to recover device values. “已观测” means collected, not a risk-control pass.
Font matching uses Canvas text width with three fallback families; it does not enumerate all fonts or hash pixels.
UA/Client Hints and Emoji family are self-reports/inferences, not proof of physical hardware or region.
Permission querying never requests coordinates or prompts for access. Its state applies to this probe origin,
not to the declared target site; guide the user to that site's own settings when they ask about its location permission.
Unsupported/error/timeout states remain distinct, and skipped modules do not count as failed checks.

## IPv6 default policy

Follow [dedicated-environment IPv6 policy](ipv6-policy.md). The report shows 待确认 with concrete disable/verify steps until the configuration is actually reviewed. Do not classify a successful IPv6 request as meeting the disabled-by-default policy. The `confirm-ipv6` command records a scoped, evidence-backed operator review; it does not disable networking.

## Read the result and act

Progress goes to stderr with fixed service names and statuses; stdout remains JSON. Report material changes to the user, not every progress line.
The command returns the report location and a curated summary. Read only `agent-summary.json` for model reasoning.
The user inspects full local `report.html`; `report.json` includes query coverage and the evidence graph.
`snapshot.private.json` and browser exports are for local tools, not chat attachments.

The human HTML opens with a compact table: check, result (通过 / 需注意 / 未完成), and advice. IPv6 policy uses 通过 / 建议关闭 / 待确认 and concrete configuration steps.
Use `assessment.overview.table_rows` for that table; unfinished browser checks appear as rows, never passes.
The main report shows the next action and a compact baseline table. Provider tables, ASN/country codes, raw scores and endpoints are under a closed evidence disclosure. Selected optional modules have their own closed disclosure and never inflate baseline counts.
Unconfirmed checks are visibly indicated without declaring them passed. The HTML is private,
not a shareable model summary. To rebuild an old scan locally without measuring again, use
`report <report.json> --snapshot <matching-snapshot.private.json> --out <new-report.html>`.
This preserves observation times and does not fill missing reputation data. Do not describe
provenance links or provider adapters as an implemented fraud detection model.

For an ordinary status request, give one sentence from `assessment.overview.headline` and then
the three-column `table_rows` table. Keep its scoped status and advice; never turn 未完成 into 通过.
Mention any additional tool gaps when needed. Do not dump raw provider tables,
ASN, country codes, diagnostic endpoints or numeric scores without their practical meaning.
Use `assessment.reputation_readings` and `conclusions` when the user asks for evidence or detail.
Keep `assessment.optional_enhancements` separate from measured results and required actions. If a selected
enhancement fails, disclose its actual provider status while preserving all successful baseline results.
Use the relevant `assessment.conclusions` only when explaining a finding, rather than repeating all conclusions. Do not ask the user
to interpret raw tables, reproduce a generic list of possibilities, or turn missing measurements
into risk alerts. `user_actions` contains configuration checks actually justified by this scan;
`tool_gaps` belongs to the tool's unfinished coverage, not to the user's fault list.
Use the evidence and scope to explain a conclusion only when needed. Never replace an incomplete
reputation check with a positive or negative account-safety verdict.
Do not recommend changing language/timezone based on their mere presence or describe hypotheses as known 上游服务商 rules.

After a relevant change, run the same scoped scan. Use
`scan-compare <before-directory> <after-directory> --same-context` only when that context is established.
The core compares IPs privately and keeps changed subjects and changed query coverage separate.
Pass findings and recheck conditions to assistance mode when the user wants to continue a procedure.

## Rehearsal and existing tools

`scan-demo --scenario conflicting-sources|missing-coverage|provider-outage` runs synthetic scenarios without requests.
Always call these results synthetic. `check`, `plan`, `explain`, `triage`, `guide`, `learn` and `lab` remain available;
use their `--help` for exact arguments. `triage` needs actual error context, not guesses from IP scores.
For a DNS-specific question, `dns --dry-run` previews a separate optional diagnostic. `dns --network`
runs one bounded `dig` invocation for Akamai's fixed diagnostic TXT name and saves a local report.
The configured DNS chain may forward resolver addresses and ECS to that authority. No credentials are used.
If `dig` is missing, report `unsupported`; do not install system tools without applicable authorization.
Read the returned summary only. Its context is `dig_default_resolver`, not the browser's DoH or all system
split-DNS routes. Cache freshness and complete DNS leakage remain unestablished; never label the whole
environment safe from this test. The plain `scan` still reports actual browser DNS as unobserved.
