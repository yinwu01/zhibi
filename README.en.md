# Zhibi · Let your agent check and prepare your 目标服务 environment

**Turn scattered setup advice into actions your agent can carry out.**

Zhibi is a local Skill for checking the environment you actually use for 目标服务. With a computer-use capable agent, it can open that browser, run checks, inspect relevant settings, carry out authorized changes and recheck the result.

**Choose the environment → Check → Assist with configuration → Verify and hand over.** No provider keys are needed for the default flow.

[Get started](#get-started) · [简体中文](README.md)

<details>
<summary>Why I built this: a personal note</summary>

## A personal note

Using 目标服务 has always been very difficult for Chinese users. Its capabilities are tempting, and we want to use it normally. But I have found that many so-called checking websites and projects mainly patch things up based on scattered feedback. With those feedback-monitoring websites in particular, you have no idea how extensively they have sold your data or to whom.

After opening three accounts and steadily using 20x Max on them, I believe we should reverse-engineer 目标服务's risk-control thinking from a risk-control perspective and take corresponding steps to address known strategies.

From a conventional risk-control perspective, the core strategy for using a product is **cosplay**: we need to disguise ourselves as normal users within the scope 目标服务 permits. As long as the user profile makes sense, the account will naturally stay safe.

Viewed this way, many current rumors are pretty ridiculous. Some people say that typing Chinese, or even using Chinese commas, gets you banned. Chinese is one of the most widely used languages in the world; banning someone just for using it would be absurd. Then there is changing timezones. Someone might change a setting on a Linux server, or their computer's clock might malfunction and cause a timezone mismatch. From a risk-control perspective, a timezone change alone cannot be a reasonable basis for a decision. If even that directly triggers enforcement, it can only be a flaw in the risk-control algorithm's design.

As it happens, I currently work in a ByteDance risk-control team focused on international products. From a risk-modeling perspective, we can absolutely infer 目标服务's risk-control policies. Once those policies are clear, we can achieve perfect cosplay: know yourself and your opponent, and win every battle.

With this project, I hope to draw on the experience of excellent existing projects and combine a risk-control perspective with community feedback to provide a complete approach to normal 目标服务 registration and use.

This project has three main parts:

1. Fully local IP checks: stop exposing your valuable data to third parties and avoid putting your registration and usage environment at further risk.
2. A risk-control evasion Skill: guidance and assistance to help you respond to 目标服务's risk-control strategies.
3. A practical tutorial for stable use: based on my experience maintaining and using three accounts reliably. For many people, this may be the most important part; the remaining checks can simply be handed to an agent to complete automatically.

That is why we are starting this project for 目标服务.

</details>

## Get started

You need Python 3.9+ and a local agent. Computer use must already be available in your host; installing this Skill does not grant that capability. Without it, the agent can still run diagnostics and ask you to complete the specific browser step.

1. Download the [complete Skill ZIP](https://github.com/JoeyWu-tech/zhibi/releases/download/v0.3.0a3/zhibi-skill.zip). This private repository requires an invited GitHub account.
2. Extract the whole `zhibi` folder into `~/.agents/skills/`. Keep assets, scripts and references. Move an older installation outside the skills directory first.
3. Start a fresh session, invoke `$zhibi` or `/zhibi`, and say:

> Check the AdsPower profile I use for 目标服务 with Zhibi. You may use the default no-key services. Operate the browser, inspect relevant settings, explain any proposed changes, apply changes within my authorization, recheck, and open the report.

No pip installation, provider registration or manual JSON copying is needed. If the browser cannot reach the local receiver, the agent can use the file-based session instead.

[Installation and first-run tutorial](tutorials/skill.md)

## What you receive

A local report showing the main conclusion, the agent's next action, and a short **Check | Result | Advice** table. Technical evidence and optional results stay collapsed. A failed measurement never becomes a zero score or a pass.

The Skill has two modes:

- **Detect:** measure the actual environment, query no-key intelligence and explain actionable findings.
- **Assist:** follow the user's task or supplied procedure, inspect settings with computer use or supported local tools, perform authorized changes, retain recovery evidence and recheck the same environment.

The default checks cover the actual exit, available IP labels/history, and the dedicated environment's IPv6 policy. Extra checks are selected for a specific question. Account verification, payment and unavailable permissions remain explicit handoffs. The founder's detailed registration procedure is still pending; it is not invented by the agent.

## Optional tools remain available

Extra providers, browser rendering observations, DNS/TLS, blocklists, connectivity diagnostics, maintenance and recovery tools remain opt-in. See the [catalog](docs/capability-coverage.md), [optional modules](tutorials/optional-modules.md), [provider setup](tutorials/providers.md) and [maintenance guide](tutorials/environment-maintenance.md). The catalog is a reference, not an onboarding checklist.

```bash
# Actual-browser default flow; add --file if this profile cannot reach loopback.
python3 ~/.agents/skills/zhibi/scripts/zhibi.py session --preset basic --network
```

For source installation, clone the repository and run `python3 scripts/install_skill.py --host codex`. The standalone [start.html](start.html) remains a manual fallback.

## Evidence and privacy

Each recommendation connects a concrete concern to an observation, its limits, an action and a recheck. Provider scores are not 目标服务 ban probabilities. Language, timezone and fonts alone do not produce a risk verdict.

Reports and private observations stay local. Network measurements and IP lookups reveal the request or queried IP to the selected services; local processing does not mean offline. 目标服务 cookies and credentials are not collected. [Privacy](docs/privacy.md) · [Upstream reuse](docs/upstream-reuse.md)

Version **0.3.0a3**, private prerelease. [Download](https://github.com/JoeyWu-tech/zhibi/releases/tag/v0.3.0a3) · [Workflow validation](docs/product-flow-validation.md)

[MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) · Independent community project; not affiliated with 上游服务商. No account outcome is guaranteed.
