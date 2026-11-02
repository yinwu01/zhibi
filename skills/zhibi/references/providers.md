# IP intelligence coverage

`providers` lists adapters and key configuration status. Do not open key files or print environment values.

| Adapter | Capability | Setup |
| --- | --- | --- |
| ipwhois | Country, ASN, organization | Public identity endpoint; no key |
| proxycheck | v3 proxy/VPN/Tor/hosting, risk score, detection confidence, available attack history, source update time | No key; 100/day; current adapter is keyless only |
| ipquery | Proxy/VPN/Tor/datacenter flags and native 0–100 risk score | No key; public free tier, subject to rate limits |
| stopforumspam | Spam database match, frequency and available last-seen time | No key; IP-only read; current daily quota not verified |
| ipapi | Identity; keyed proxy/VPN/Tor/hosting/abuse flags and network abuse ratios | Anonymous response is identity-only; optional `ZHIBI_IPAPI_KEY` |
| ipqs | IP fraud score, proxy/VPN/Tor and recent-abuse fields | `ZHIBI_IPQS_KEY` |
| abuseipdb | Abuse confidence, report/reporter counts and recent report time | `ZHIBI_ABUSEIPDB_KEY` |

Use `scan --network --reputation` for the fixed no-key preset (ipwhois/proxycheck/ipquery/stopforumspam).
It works without reading a key store. Do not stop at anonymous ipapi identity-only coverage.
IPQS, AbuseIPDB and ipapi.is are optional enhancements. Complete a default check without requesting keys.
Only explain configuration when the user wants an enhancement; choosing one does not require the others.
Do not classify an unselected or unconfigured optional provider as a failed baseline check or required task.
Add only the user-selected keyed sources explicitly; having a configured key is not automatic opt-in.
Key does not mean paid: ipapi free key is 1,000/day; IPQS advertises
1,000 free credits/month; AbuseIPDB individual free plan has 1,000 Checks/Reports per day.
Verified 2026-10-19; tiers can change. ProxyCheck offers 1,000/day with a free key but this adapter
does not implement its keyed endpoint. Do not invent header authentication or place a key in a URL.

## Optional setup guide

Explain what the selected source adds, then direct the user to its own registration page:

- IPQS: [free account](https://www.ipqualityscore.com/create-account); IP fraud score, proxy tags and recent-abuse flags.
- AbuseIPDB: [free Individual account](https://www.abuseipdb.com/register?plan=free); 30-day report/reporter counts and last report time.
- ipapi.is: [free account](https://ipapi.is/app/signup); extra network/proxy tags and company/ASN abuse ratios.

The user completes registration and verification, retrieves their key from the provider dashboard, and
enters it in their own terminal with `python3 <skill>/scripts/zhibi.py configure <provider>`.
Use `configure all` for the three-key wizard; it preserves existing keys and allows blank input to skip.
Do not run the interactive wizard in an Agent-captured session. Configuration is not API validation;
perform the authorized scan after the user finishes. If hidden input is unavailable, the wizard refuses input.
For example, if the user chose IPQS, add `--provider ipqs` to the existing
`scan --network --reputation` command, preserving the actual browser target and freshly measured browser export.
Verify the response's status; saving a key alone does not prove authentication or field availability.
Input is hidden and stored in `~/.zhibi/providers.json` with private permissions. Never request keys in chat.
The core also supports the named environment variables. It does not search `.env` files or account credentials.
IPQS and AbuseIPDB use headers; ipapi uses a JSON POST body. Keys never appear in request URLs or reports.

Each selected provider is queried once per measured address (maximum two with IPv6), without retries or fallback.
Subscription, quotas and available fields depend on the provider. The Skill does not purchase services.
Absent fields remain unknown; do not infer missing labels from ASN, country or another provider.

Preserve score semantics:

Zero is a valid provider response, never a default for missing data. A zero risk score is the low end of
that provider's scale, not completion progress or proof that the browser is not using a proxy.

- IPQS `fraud_score`: IP-only query with `strictness=0` and `allow_public_access_points=true`.
- ipapi `company_abuse_ratio` / `asn_abuse_ratio`: network-level proportions, not individual account probability.
- AbuseIPDB `abuse_confidence`: confidence derived from abuse reports; this adapter requests a 30-day window.
- ProxyCheck `proxycheck_risk`: v3 network/activity risk, not a fraud probability. Confidence is a separate field.
  Default observation horizon varies by source; `attack_history=null` means unavailable, never zero.
- IPQuery `ipquery_risk`: native malicious-activity risk indicator; no documented threshold here, so do not borrow IPQS thresholds.
- StopForumSpam `spam.frequency`: entries in its spam dataset; no fixed window in this request.
  A miss is not proof of no attacks in other databases. Last-seen wall time has no supplied timezone.

The free-source result can be useful even when optional IPQS/AbuseIPDB are unconfigured. Report actual
labels, scores and spam findings first; name the exact extra coverage a free key would unlock.

`queried_at` is our query time; `source_updated_at` stays unknown unless supplied.
Shared upstream data means agreeing providers are not necessarily independent evidence.
Preserve failures and conflicts while using the remaining selected sources.
