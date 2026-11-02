# Optional tools shipped with the Skill

Use `python3 <skill>/scripts/zhibi.py`; `--help` gives exact arguments. Basic needs only Python 3.9+. Every item here is optional.

## Complete or selected detection

- `session --preset all --network --out <new-dir>`: open the temporary URL in the actual browser/profile, run selected checks and save locally. Generates `<new-dir>/report/report.html` and a curated Agent summary. Never serve private reports over HTTP.
- If loopback fails, `session --file --preset all --network` generates a local HTML with the same choices. Open it in the same profile and save; only its random per-run filename in `~/Downloads` is watched. For a custom download location, copy the selected export to the printed `save_download_as` path using the core, without reading raw JSON into model context.
- `suite --preset all --network --out <new-dir>`: checks the collector. To use a browser export, add `--browser <file> --target browser`.
- `suite --preset custom --module feeds --provider ip2location --network`: only selected extras/providers. `modules` lists all 13 modules; `suite --dry-run` previews requests. No `--network` means no external requests.
- `all` never changes system/browser settings, installs software, prompts for credentials or requires all services. Unconfigured keys are skipped before requests; tell the user which selected data could not be obtained, without failing completed basic checks.

| Module | What it measures | Dependency / boundary |
| --- | --- | --- |
| native / cli | Collector OS/CPU/language/proxy switches; 目标客户端 version/channel | Local; not necessarily the browser host |
| browser-extras | Canvas stability/private hash, WebGL, offline Audio, TLS, DNS | Browser v4 export; TLS uses tls.peet.ws, DNS needs the user's observer |
| checkcc-model | Pinned MIT CheckCC regional model and client-weight comparison | Research only; does not change Zhibi verdict or imply 上游服务商 policy |
| dns | Terminal resolver/ECS | dig + whoami.ds.akahelp.net; not browser DNS |
| dnsbl | Spamhaus/SpamCop membership with response/control validation | dig and permitted resolver; errors are not listings |
| feeds | IPsum and Spamhaus DROP membership | Downloads public lists then compares locally; queried IP is not sent in URL |
| services / smtp | Public HTTP responses; fixed SMTP TCP ports | Collector path only; no authentication, email sending or content-unlock verdict |
| tls | Collector TLS/HTTP observation | tls.peet.ws; not browser fingerprint |
| route | Explicit proxy/interface IPv4 egress | curl; private config; no fallback to direct |
| mmdb | Offline database lookup + build metadata | User-supplied licensed MMDB; optional maxminddb package |
| expected-egress | Measured selected IP equals user's expected IP | Private config; no model-visible IP |

Browser rendering values stay in private local artifacts. Read `agent-summary.json`, not `modules.private.json`, browser exports or credentials. The HTML retains the three-column result/action table. A model score or a collected fingerprint is an observation, not a pass/fail account decision.

## Optional providers

Original no-key preset: ipwhois, proxycheck, ipquery, stopforumspam. Additional no-key options: ip2location and dbip; anonymous ipapi may provide identity only. Keyed options: ipapi, ipqs, abuseipdb, ipinfo (free Lite token), ipregistry, scamalytics and scamalytics-us. Paid fields remain unknown when absent.

The user runs `configure <provider>` in their own terminal and enters the key hidden; never ask them to paste a key into chat. `configure all` remains the original three optional providers. Scamalytics requires `username:api-key` for the account's EU/US node; the official API puts its key in an HTTPS query string. The core omits request URLs, exception bodies and credentials from output. IP2Location's native fraud scale is 0–99; other native scales are preserved. Do not average scores or count aggregated sources as independent votes.

## Maintenance and delivery

| Entry point | Default / explicit action | Recheck |
| --- | --- | --- |
| `maintain ipv6`, `timezone`, `locale`, `cli-repair` | Plan first; `--apply` writes only selected setting/version and saves receipt | `maintain restore <receipt>`; then actual same-environment measurement |
| `adspower inspect/update/restore --config <file>` | Optional authenticated loopback Local API; update refuses an active profile | Read original values, keep receipt; free users can use session without API |
| `workspace cache/cache-restore` | Closed selected directory; quarantine/restore only allowlisted caches | Does not read or change cookie storage |
| `workspace backup/restore/empty` | User-selected closed directory; local AES-GCM archive needs cryptography and a terminal password | Keep archives/password out of model context; empty/restore preserves prior local directory, not encrypted automatically |
| `network-setup client-config/ssh-tunnel` | Generate private Mihomo config or strict-known-host SSH plan | No automatic VPS purchase, remote installation, TUN or firewall changes; this is not full CCBaga VPS deployment |
| `suite-share` | Redacted HTML/TXT/JSON local preview, zh/en | No automatic upload or built-in screenshot capture |
| `suite-compare` | Compare scoped base evidence and module status | Does not claim comparison of all raw browser values |
| `skill-install/skill-rollback` | Verify official SHA256; explicit replacement preserves previous version | Run doctor and a local check after upgrade |

A successful setting write is not proof of effective routing. Cross-platform write adapters were fixture-tested; do not claim live Windows/Linux validation. Self-hosted browser DNS requires a delegated zone, DNS listener and wildcard HTTPS reverse proxy; its collector does not establish whether DoH was used. Full VPS deployment, all proxy-client controls and full streaming-region unlock detection remain outside implemented coverage.
