# Third-party code in Zhibi

## CCBaga

- Copyright (c) 2026 CCBaga contributors. MIT; full text: [licenses/CCBaga-MIT.txt](licenses/CCBaga-MIT.txt).
- Commit: `30a171f5191fbb65dc24e4b1a0392d998f7c5719`.
- Source: `src/browser-network.ts`; corresponding parsing/request tests informed migration tests.
- Adapted in `src/zhibi/assets/network-probe.js`: IP validation and bounded browser egress fetching.
- Changes: two explicit address families; no automatic alternate endpoint; omit credentials/referrer; bounded streaming body; fixed error states rather than raw exception strings.
- No Chromium engine, UI assets, vendored components, deployment or identity-changing operations were copied.

## CheckCC

- Copyright (c) 2026 yacuo / CheckCC. MIT; full text: [licenses/CheckCC-MIT.txt](licenses/CheckCC-MIT.txt).
- Commit: `078e7baa1d2a08df28da3f25dacb90e687f4c79f`.
- Source: `src/detection/client-engine.ts`, environment collection, fixed font probe and browser/device token lists.
- Adapted in `src/zhibi/assets/network-probe.js`: language, timezone, locale, user-agent and browser-brand observation.
- Also adapted in `src/zhibi/assets/browser-details.js`: fixed 26-font candidate list and Canvas text-width probing, browser/device token matching, and language/UTC offset observation.
- Changes: independent opt-in modules, bounded fields, failure isolation, unstable-font-metric detection, explicit unknown language script, fixed-vocabulary summaries and local-only values. The optional `checkcc_model.py` also ports `scoring.ts`, `config/regions.ts`, `config/signals.ts` and client contribution logic from `client-engine.ts`. Research scores are separately labeled, unavailable observations stay unknown, and they never determine the main verdict. No browser-fingerprint manipulation was copied. Emoji family is labeled as UA inference, not rendered-pixel measurement.

Upstream file digests are recorded in [docs/upstream-lock.json](docs/upstream-lock.json). Both full MIT notices are embedded in exported advanced browser pages and included in the Skill distribution. IPQuality is a researched reference; no AGPL code is incorporated.

## External reputation services

The IPWhois, ipapi.is, IPQS, AbuseIPDB, ProxyCheck, IPQuery, StopForumSpam, IPinfo, IPregistry, IP2Location.io, DB-IP and Scamalytics adapters are independently
implemented API clients. No service database, shared credential or proprietary scoring model is distributed.
Each service's terms and data policies apply to its responses independently of this project's MIT license.
These adapters are not claimed to be copied from CCBaga or CheckCC.

Public IPsum and Spamhaus DROP data are optionally downloaded for local comparison, not included in the distribution. Data terms apply separately. DB-IP Free lookups retain the attribution “IP Geolocation by DB-IP” with its source link. AdsPower API and system maintenance adapters are independent implementations.
