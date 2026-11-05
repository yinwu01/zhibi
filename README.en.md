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

Switching machines, network exits and browser profiles can leave settings out of sync. Zhibi grew out of my experience studying risk controls for international applications and using paid services across different environments. The practical aim is to inspect those settings, prepare a dedicated environment, and verify the resulting network path.

The project combines three parts:

1. Local environment checks and reports, with explicit network queries when needed.
2. An Agent Skill that interprets observations and carries out configuration steps.
3. A dedicated VPS application workspace and browser connection, with reusable startup, shutdown and recovery instructions.

</details>

## Get started

You need Python 3.9+ and a local agent. Computer use must already be available in your host; installing this Skill does not grant that capability. Without it, the agent can still run diagnostics and ask you to complete the specific browser step.

The public source can be installed now:

```bash
git clone https://github.com/yinwu01/zhibi.git
cd zhibi
python3 scripts/install_skill.py --host codex
```

The installer builds the complete Skill and refuses to overwrite an existing installation. Other hosts can use `--dest /path/to/skills/zhibi`. The v0.4.0a1 release is currently a draft; use source installation for now.

Start a fresh session, invoke `$zhibi` or `/zhibi`, and say:

> Check the AdsPower profile I use for the application with Zhibi. You may use the default no-key services. Operate the browser, inspect relevant settings, explain any proposed changes, apply changes within my authorization, recheck, and open the report.

No pip installation, provider registration or manual JSON copying is needed. If the browser cannot reach the local receiver, the agent can use the file-based session instead.

[Installation and first-run tutorial](docs/archive/tutorials/skill.md)

## What you receive

A local report showing the main conclusion, the agent's next action, and a short **Check | Result | Advice** table. Technical evidence and optional results stay collapsed. A failed measurement never becomes a zero score or a pass.

The Skill has two modes:

- **Detect:** measure the actual environment, query no-key intelligence and explain actionable findings.
- **Assist:** follow the user's task or supplied procedure, inspect settings with computer use or supported local tools, perform authorized changes, retain recovery evidence and recheck the same environment.

The default checks cover the actual exit, available IP labels/history, and the dedicated environment's IPv6 policy. Extra checks are selected for a specific question. Account verification, payment and unavailable permissions remain explicit handoffs.

## Optional tools remain available

Extra providers, browser rendering observations, DNS/TLS, blocklists, connectivity diagnostics, maintenance and recovery tools remain opt-in. See the [catalog](docs/architecture/capability-coverage.md), [optional modules](docs/archive/tutorials/optional-modules.md), [provider setup](docs/archive/tutorials/providers.md) and [maintenance guide](docs/archive/tutorials/environment-maintenance.md). The catalog is a reference, not an onboarding checklist.

```bash
# Actual-browser default flow; add --file if this profile cannot reach loopback.
python3 ~/.agents/skills/zhibi/scripts/zhibi.py session --preset basic --network
```

The standalone [start.html](start.html) remains a manual fallback.

## Evidence and privacy

Each recommendation connects a concrete concern to an observation, its limits, an action and a recheck. Provider scores are not account-enforcement probabilities. Language, timezone and fonts alone do not produce a risk verdict.

Reports and private observations stay local. Network measurements and IP lookups reveal the request or queried IP to the selected services; local processing does not mean offline. Application cookies and credentials are not collected. [Privacy](docs/reference/privacy.md) · [Upstream reuse](docs/research/upstream-reuse.md)

Public development prerelease; source installation is available now. Release archives will be published separately. [Workflow validation](docs/implementation/acceptance-matrix.md)

[MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) · Independent community project; not affiliated with application vendors. No account outcome is guaranteed.

## Acknowledgments

Thanks to the authors and contributors of these projects:

- [xiaoxiaodong-vps](https://github.com/nevertoday/xiaoxiaodong-vps): VPS deployment blueprints, Agent Skill organization and operational workflows.
- [CCBaga](https://github.com/liseami/CCBaga): network and environment workflows, and adapted browser-egress detection code.
- [CheckCC](https://github.com/yacuo/check-cc): adapted browser observations, font probes and research comparison models.
- [IPQuality](https://github.com/xykt/IPQuality): research and capability comparison for IP quality checks.
- [bubblewrap](https://github.com/containers/bubblewrap): the Linux process isolation tool used by application workspaces.
- [graftcp](https://github.com/hmgle/graftcp): proxy connectivity for applications and their child processes.

See the [upstream reuse record](docs/research/upstream-reuse.md) for versions and modifications, and [third-party notices](THIRD_PARTY_NOTICES.md) for attribution and licensing.
