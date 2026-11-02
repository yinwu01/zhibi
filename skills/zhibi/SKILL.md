---
name: zhibi
description: Check the actual environment used for 目标服务, install and configure a user-chosen fingerprint browser, remeasure, then judge whether each remaining problem is technical, channel or compliance. Use for 目标服务 environment preparation, IP checks, setup assistance and rechecks.
---

# 知彼 · 搜、装、配、验、判

One task ends when the user knows three things: what state their environment is in, what you actually changed, and which category each remaining problem belongs to. The bundled detectors support this flow; the optional catalog is not the flow.

Authoritative definition: `docs/product-definition.md` in the repository. It is not shipped inside the Skill, so it is named here rather than linked.

## Boundaries — read before acting

- **Never recommend, rank or endorse a VPS, proxy or fingerprint browser.** Present criteria and readings; the user selects. No affiliate, referral or paid placement anywhere in your output.
- **Never provide region-circumvention or risk-avoidance capability.** A region mismatch is `compliance`: the conclusion is stop, and there is no technical fix.
- **Never manage multiple account identities**, register accounts, pass verification or handle payments.
- **Never promise a pass, anonymity or account safety.** Unmeasured ≠ passed. A clean reading means only that the measured items matched.
- **Never download from third-party mirrors, repacks or cracked builds.** If the official channel is unreachable, stop and say so.

## Six stages

```
S0 受理 → (S1 搜 → S2 装)? → S3 配 → S4 验 → S5 判 → report
              ↑___________________|  (recheck loop on failure)
```

| | Stage | Do | Gate |
|---|---|---|---|
| S0 | Intake | Build a holdings list: where the user is, which devices, whether they already have an exit and a browser. Decide full flow or a degraded path. | Ask when unclear. Never guess the region or the setup. |
| S1 | Discover | Only when the user has no fingerprint browser. Search by criteria, emit a candidate table with which criteria each one meets, what authorization it needs and what it costs. | **Stop and let the user choose.** Never pick for them. |
| S2 | Acquire | Download from the official channel, verify, install, smoke-test (launches, accepts a proxy, can export readings). | Record source URL, version, hash, time. No hash → mark "no verification evidence available". No official source → stop. |
| S3 | Configure | Set proxy/exit, timezone, language, UA/platform, fonts, WebRTC policy. Snapshot first. | **No snapshot, no change.** Every change is reversible. |
| S4 | Verify | Measure again, as a separate step from configuring. | **No new measurement, no pass.** Never mark `pass` from a configuration action. |
| S5 | Judge | Assign every reading to technical / channel / compliance, then report. | No classification, no report. |

## Four states

Every measured item is exactly one of these. Never merge, never omit:

- `pass` — measured and matched
- `changed_unverified` — changed, then **not** remeasured
- `fail` — measured and did not match
- `not_measured` — not measured

`not_measured` never collapses into `pass`. Report the four counts separately.

## Classify, don't score

| Type | When | Next step |
|---|---|---|
| Technical | Caused by local or environment configuration, testable and fixable | Fix, snapshot first, then remeasure |
| Channel | Exit type, region ownership or account channel; not fixable locally | Give criteria and the self-help path. No vendor recommendations. |
| Compliance | Unsupported region, sanctioned region, terms-prohibited use | **Stop.** Say plainly that no configuration resolves it. |

A finding needs an observable object, its source and time, a practical consequence, and a recheck condition. Provider labels and scores are limited evidence, not 上游服务商's internal rules. Language, timezone or font observations alone never justify a change. Shared IPs do not establish account identity.

## Degraded paths are normal

| Path | Trigger | Do |
|---|---|---|
| D1 | Host has no computer use | Run the scripts; give step-by-step instructions for interface work only; resume at S4 when readings arrive |
| D2 | Browser can only export manually | Use the `generic_export` base; the user imports the file; you judge it |
| D3 | User wants checks only | Skip S3; go S4 → S5 |

Name the path you used in the report.

## How to fail honestly

Say the failure in one sentence, then stop. Never work around it silently.

- Cannot reach the official download: "我拿不到官方安装包，不会从第三方镜像下载。" Then wait for the user's file.
- Cannot operate the browser: "这个宿主没有 computer use，接下来这几步需要你操作，我等你回来。"
- No new measurement: "配置已改动，但还没有新的测量读数，所以现在不能算通过。"
- Region mismatch: "这不是时区或指纹能修的问题，属于地区限制，改配置解决不了。"
- Not verified: "这项没有独立验证依据，我记成未测量，不记成通过。"

## Run it

1. Resolve `python3 <this-skill>/scripts/zhibi.py` from this file's directory (Windows: `py -3`), then run `doctor`. Needs Python 3.9+, no pip. Read [setup](references/setup.md) if it fails.
2. For a web/browser task, run `session --preset basic --network --out <new-directory>` under the user's existing authorization for the named no-key services. The returned URL belongs in the **actual browser/profile**, not a convenient substitute. Use `--file` when that environment cannot reach loopback.
3. With computer use, operate the interface yourself: open the probe, click 开始检查, wait for a visible result, save to the local Skill. A download is an intermediate step, not delivery.
4. Read only the curated `agent-summary.json` (notably `base.assessment.overview`) and open `report.html` locally. Then remeasure the **same** environment after any change. Do not make cosmetic changes to obtain green rows.
5. End with: the current conclusion, what you actually completed, any exact handoff, the four state counts, the clickable report, and the recheck condition.

## Keep data and scope honest

- Default no-key intelligence: IPWhois, ProxyCheck, IPQuery, StopForumSpam; ipify measures the exit. **Their services see the request and query IPs** — say so when using them. No cookies, passwords, sessions, verification codes or payment data are collected.
- `--preset all` only on an explicit request for the expanded suite. Keys already on disk do not authorize extra recipients. IPQS, AbuseIPDB and ipapi.is are optional; never ask a new user to register them for the default flow.
- For a dedicated environment, inspect the effective IPv6 configuration before confirming it. Timeout, filtered DNS or disabled WebRTC does not prove IPv6 is blocked. Read [IPv6 policy](references/ipv6-policy.md).
- Keep browser exports, raw snapshots and provider keys inside local tools; use paths and fixed summaries in model context.
- Computer use is supplied by the host. This Skill does not install it or grant permissions.

## Load only what the task needs

- [Detection](references/detection.md): measurement, export and comparison.
- [Assistance](references/assistance.md): computer-use operation, scoped configuration, verification.
- [IPv6](references/ipv6-policy.md): evidence needed to confirm the dedicated policy.
- [Optional tools](references/optional-tools.md): extra modules, providers, maintenance, only after a relevant need or explicit selection.
- [Interpretation](references/interpretation.md): source disagreements and score meanings.
- [Providers](references/providers.md): user-chosen optional keys and privacy boundaries.

The founder's detailed registration procedure has not yet been supplied. Use an actual user-provided procedure or established preparation steps; record new ones with [the template](references/workflow-template.md). Follow official registration processes and do not invent identities.
