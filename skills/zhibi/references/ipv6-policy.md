# Dedicated-environment IPv6 policy

Default recommendation: disable or block IPv6 outbound traffic in the dedicated environment when it is not needed.
This reduces unmanaged outbound paths; it is a Zhibi network-privacy policy, not a known 上游服务商 requirement.

## Give an actionable result

- No reviewed configuration evidence: show **待确认** and tell the user to disable IPv6 outbound in the dedicated environment's proxy client or egress firewall, save/restart that environment, and verify the effective setting.
- IPv6 is reachable: show **建议关闭** under this default policy. Connectivity is not confirmation that the route is managed.
- Reviewed configuration confirms disabled/blocked, and the same scan has no contradictory IPv6 success: show **通过**, scoped to that configuration review.
- Timeout, DNS error, zero ICE candidates, WebRTC disabled, “prefer IPv4,” or filtered AAAA answers alone cannot establish that IPv6 outbound is disabled.

## Apply only within the agreed environment

Identify the actual browser/profile and the proxy client, dedicated VM/container, or scoped egress rules it uses.
Inspect the software's current documentation and effective configuration; do not invent an AdsPower IPv6 switch.
If it offers an IPv6 outbound/IPv6 protection control, disable IPv6 outbound there and save/restart the dedicated environment.
If it does not, use an authorized dedicated-environment egress rule that blocks IPv6 traffic. A system proxy alone is not such a rule.
Do not disable IPv6 across the user's everyday host by default. If the environment is not independently controllable,
explain the required isolation instead of changing unrelated network settings. Configuration changes require existing task authorization.
Users who need IPv6 can choose a separately verified dual-stack setup; do not silently claim it meets this disabled-by-default policy.

## Record a real configuration review

After the setting takes effect, run a fresh check in that same environment and inspect the effective configuration.
Retain a local screenshot or configuration file showing the disabled/blocked setting and its environment scope.
Do not use a detection failure screenshot as configuration evidence. Do not put credentials in chat.
Then, within 15 minutes of that scan, record the review:

```bash
python3 <skill>/scripts/zhibi.py confirm-ipv6 <scan-directory> \
  --evidence <local-settings-screenshot-or-config-file> \
  --configuration blocked --method local_config --reviewed \
  --out <new-confirmed-directory>
```

Use `disabled` for a disabled setting, or `blocked` for an effective outbound block; use `settings_ui` for a settings-screen review.
The command **records the operator's review**. It hashes the evidence and binds it to that scan; it does not inspect arbitrary
firewall syntax or independently prove the claim. Never use `--reviewed` unless you actually performed that review.
It writes a new report and leaves the original intact, sends no requests and changes no settings.
Paths to evidence remain in `ipv6-evidence.private.json`; only fixed conclusions enter the Agent summary.
Old scan data, another environment's evidence, and a successful IPv6 observation must not be reused to create a pass.
New scans require a new review. Read the resulting `assessment.overview.table_rows` for the user-facing table.

Basis: [RFC 7359](https://www.rfc-editor.org/rfc/rfc7359.html) describes dual-stack VPN traffic bypass and mitigation;
[Microsoft guidance](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/configure-ipv6-in-windows)
explains why blanket host-level disabling is not the default recommendation.
