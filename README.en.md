# Zhibi · Let your agent prepare your network environment

**Turn scattered setup advice into actions your agent can carry out.**

Zhibi is a local Skill for checking the environment you actually use for the application. With a computer-use capable agent, it can open that browser, run checks, inspect relevant settings, carry out authorized changes and recheck the result.

**Scan → Ask whether configuration is needed → Prepare the VPS and application → Configure the selected browser → Verify and hand over.** No provider keys are needed for the default flow.

[Get started](#get-started) · [简体中文](README.md)

The full workflow provides two coordinated environments: a dedicated Linux application workspace on your VPS, and a separate local browser profile using that VPS's network path. Configure the chosen timezone and languages, keep the visible settings consistent, and reduce exposure from unrelated local accounts, extensions and permissions.

**A Linux VPS you are authorized to manage is required for the full workflow.** Residential or datacenter connectivity can be used; a mass-shared proxy subscription is not a substitute for the server or a dedicated, traceable exit. Local checks can run before you have a VPS.

## Application workspace and persistent service

`process-workspace` creates a separate HOME, environment and filesystem view with bubblewrap. `process-entry` creates a normal command entry outside the application's installation directory, so replacing the application at the same path retains the wrapper. Proxy mode uses a pinned graftcp binary and a private Unix SOCKS5 endpoint inside a network namespace without an external route.

`proxy-gateway` supplies that endpoint using the server's existing TCP egress. `runtime-service` exports a standalone systemd user-service manager, optionally supervising a background application together with the gateway. Install, status and rollback commands are included; existing services are not overwritten. Interactive applications use the command entry rather than a background service.

Linux checks cover command replacement, child processes, DNS, TCP, direct UDP blocking, real HTTPS, gateway failure, systemd restart and rollback. Final application operations and the selected fingerprint browser still require their own acceptance checks. See [runtime implementation and evidence](docs/implementation/process-wrapper.md).

<details>
<summary>Why I built this: a personal note</summary>

## A personal note

Using the application has always been very difficult for Chinese users. Its capabilities are tempting, and we want to use it normally. But I have found that many so-called checking websites and projects mainly patch things up based on scattered feedback. With those feedback-monitoring websites in particular, you have no idea how extensively they have sold your data or to whom.

After opening three accounts and steadily using 20x Max on them, I believe we should reverse-engineer the application's risk-control thinking from a risk-control perspective and take corresponding steps to address known strategies.

From a conventional risk-control perspective, the core strategy for using a product is **cosplay**: we need to disguise ourselves as normal users within the scope the application permits. The practical target is a consistent observable environment, with fewer unnecessary sources of local-device information.

Viewed this way, many current rumors are pretty ridiculous. Some people say that typing Chinese, or even using Chinese commas, gets you banned. Chinese is one of the most widely used languages in the world; banning someone just for using it would be absurd. Then there is changing timezones. Someone might change a setting on a Linux server, or their computer's clock might malfunction and cause a timezone mismatch. From a risk-control perspective, a timezone change alone cannot be a reasonable basis for a decision. If even that directly triggers enforcement, it can only be a flaw in the risk-control algorithm's design.

As it happens, I currently work in a ByteDance risk-control team focused on international products. From a risk-modeling perspective, we can absolutely infer the application's risk-control policies. This motivates the project: investigate observable signals, configure a coherent environment, and verify what actually changed.

With this project, I hope to draw on the experience of excellent existing projects and combine a risk-control perspective with community feedback to provide a complete approach to normal the application registration and use.

This project has three main parts:

1. Fully local IP checks: stop exposing your valuable data to third parties and avoid putting your registration and usage environment at further risk.
2. A risk-control evasion Skill: guidance and assistance to help you respond to the application's risk-control strategies.
3. A practical tutorial for stable use: based on my experience maintaining and using three accounts reliably. For many people, this may be the most important part; the remaining checks can simply be handed to an agent to complete automatically.

That is why we are starting this project for the application.

</details>

## Get started

You need Python 3.9+ and a local agent. Computer use must already be available in your host; installing this Skill does not grant that capability. Without it, the agent can still run diagnostics and ask you to complete the specific browser step.

The public source can be installed now:

```bash
git clone https://github.com/yinwu01/zhibi.git
cd zhibi
python3 scripts/install_skill.py --host codex
```

The installer builds the complete Skill and refuses to overwrite an existing installation. Other hosts can use `--dest /path/to/skills/zhibi`. Once a release archive is published, extracting its entire `zhibi` folder into the host's skill directory is an alternative.

Start a fresh session, invoke `$zhibi` or `/zhibi`, and say:

> Check the AdsPower profile I use for the application with Zhibi. You may use the default no-key services. Operate the browser, inspect relevant settings, explain any proposed changes, apply changes within my authorization, recheck, and open the report.

No pip installation, provider registration or manual JSON copying is needed. If the browser cannot reach the local receiver, the agent can use the file-based session instead.

[Installation and first-run tutorial](docs/archive/tutorials/skill.md)

## What you receive

A local report showing the main conclusion, the agent's next action, and a short **Check | Result | Advice** table. Technical evidence and optional results stay collapsed. A failed measurement never becomes a zero score or a pass.

The Skill has two modes:

- **Detect:** measure the actual environment, query no-key intelligence and explain actionable findings.
- **Assist:** follow the user's task or supplied procedure, inspect settings with computer use or supported local tools, perform authorized changes, retain recovery evidence and recheck the same environment.

The default checks cover the actual exit, available IP labels/history, and the dedicated environment's IPv6 policy. Extra checks are selected for a specific question. Account verification, payment and unavailable permissions remain explicit handoffs. The founder's detailed registration procedure is still pending; it is not invented by the agent.

## Optional tools remain available

Extra providers, browser rendering observations, DNS/TLS, blocklists, connectivity diagnostics, maintenance and recovery tools remain opt-in. See the [catalog](docs/architecture/capability-coverage.md), [optional modules](docs/archive/tutorials/optional-modules.md), [provider setup](docs/archive/tutorials/providers.md) and [maintenance guide](docs/archive/tutorials/environment-maintenance.md). The catalog is a reference, not an onboarding checklist.

```bash
# Actual-browser default flow; add --file if this profile cannot reach loopback.
python3 ~/.agents/skills/zhibi/scripts/zhibi.py session --preset basic --network
```

For source installation, clone the repository and run `python3 scripts/install_skill.py --host codex`. The standalone [start.html](start.html) remains a manual fallback.

## Evidence and privacy

Each recommendation connects a concrete concern to an observation, its limits, an action and a recheck. Provider scores are not the application ban probabilities. Language, timezone and fonts alone do not produce a risk verdict.

Reports and private observations stay local. Network measurements and IP lookups reveal the request or queried IP to the selected services; local processing does not mean offline. the application cookies and credentials are not collected. [Privacy](docs/reference/privacy.md) · [Upstream reuse](docs/research/upstream-reuse.md)

Public development prerelease; source installation is available now. Release archives will be published separately. [Workflow validation](docs/implementation/acceptance-matrix.md)

[MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) · Independent community project; not affiliated with application vendors. No account outcome is guaranteed.
