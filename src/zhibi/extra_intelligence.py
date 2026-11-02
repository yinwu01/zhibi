"""Official optional APIs. No website scraping or pooled third-party credentials."""
import re
import urllib.parse


def spec(name, host, env, docs, purpose, required=True, sources=(), profile=None):
    return dict(name=name, host=host, key=env, docs=docs, purpose=purpose,
                key_required=required, upstream_sources=list(sources), profile=profile or {})


SPECS = {
    "ipinfo": spec("IPinfo Lite", "api.ipinfo.io", "ZHIBI_IPINFO_KEY", "https://ipinfo.io/developers/lite-api", "network_identity"),
    "ipregistry": spec("IPregistry", "api.ipregistry.co", "ZHIBI_IPREGISTRY_KEY", "https://ipregistry.co/docs", "proxy_and_network_intelligence"),
    "ip2location": spec("IP2Location.io", "api.ip2location.io", "ZHIBI_IP2LOCATION_KEY", "https://www.ip2location.io/ip2location-documentation", "proxy_and_network_intelligence", False),
    "dbip": spec("DB-IP Free", "api.db-ip.com", None, "https://db-ip.com/api/free.php", "country_identity", False),
    "scamalytics": spec("Scamalytics EU", "api12.scamalytics.com", "ZHIBI_SCAMALYTICS_KEY", "https://docs.scamalytics.com/ip-fraud-risk-api/v3/", "aggregated_fraud_intelligence", sources=("ipinfo:geolocation", "maxmind:geolocation", "ip2location:proxy", "dbip:geolocation"), profile={"node": "EU", "api": "v3"}),
    "scamalytics-us": spec("Scamalytics US", "api11.scamalytics.com", "ZHIBI_SCAMALYTICS_US_KEY", "https://docs.scamalytics.com/ip-fraud-risk-api/v3/", "aggregated_fraud_intelligence", sources=("ipinfo:geolocation", "maxmind:geolocation", "ip2location:proxy", "dbip:geolocation"), profile={"node": "US", "api": "v3"}),
}
NOTES = {
    "ipinfo": "需免费 Lite Token；只有国家/ASN，无付费代理标签。",
    "ipregistry": "需自己的 Key；试用额度及持续使用费用以账户套餐为准。",
    "ip2location": "可免 Key 查询；免费 Key 可提高额度，付费字段缺失不会按零处理。",
    "dbip": "免 Key Free API；仅地区归属，不提供 ASN 或欺诈分。IP Geolocation by DB-IP。",
    "scamalytics": "需 EU 节点账户；隐藏输入 username:api-key。按套餐收费；服务要求 Key 在 HTTPS 查询串中，本工具不记录 URL。",
    "scamalytics-us": "需 US 节点账户；隐藏输入 username:api-key。按套餐收费；服务要求 Key 在 HTTPS 查询串中，本工具不记录 URL。",
}


def request(provider, address, key, headers):
    from .intelligence import QueryFailure
    quoted = urllib.parse.quote(address, safe="")
    if provider == "ipinfo":
        headers["Authorization"] = "Bearer " + key
        return "https://api.ipinfo.io/lite/" + quoted, None
    if provider == "ipregistry":
        headers["Authorization"] = "ApiKey " + key
        return "https://api.ipregistry.co/" + quoted, None
    if provider == "ip2location":
        if key:
            headers["Authorization"] = "Bearer " + key
        return "https://api.ip2location.io/?" + urllib.parse.urlencode({"ip": address}), None
    if provider == "dbip":
        return "https://api.db-ip.com/v2/free/" + quoted, None
    username, sep, secret = (key or "").partition(":")
    if not sep or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", username) or not secret:
        raise QueryFailure("auth_error")
    return "https://" + SPECS[provider]["host"] + "/v3/" + username + "?" + urllib.parse.urlencode({"key": secret, "ip": address}), None


def parse(provider, data, address, facts):
    from .intelligence import QueryFailure, mapping, country, text, flag, number, as_number, public_ip
    if data.get("error") or data.get("errorCode") or data.get("code"):
        raise QueryFailure("error")
    if provider.startswith("scamalytics"):
        source = mapping(data.get("scamalytics"))
        if source.get("status") != "ok":
            raise QueryFailure("error")
        if public_ip(source.get("ip")) != address:
            raise QueryFailure("invalid_response")
        proxy = mapping(source.get("scamalytics_proxy"))
        for target, name in (("vpn", "is_vpn"), ("hosting", "is_datacenter"), ("proxy", "is_resproxy")):
            facts["flags"][target] = flag(proxy.get(name))
        facts["flags"]["recent_abuse"] = flag(source.get("is_blacklisted_external"))
        value = number(source.get("scamalytics_score"), 100)
        if value is not None:
            facts["scores"].append(dict(name="scamalytics_score", value=value, scale=100, scope="ip_query"))
        # Do not silently pick one of the aggregated geolocation sources as ground truth.
        org = source.get("scamalytics_org")
        facts["organization"] = text(org) if org and not org.startswith("PREMIUM FIELD") else None
        return facts, "official_api"
    field = "ipAddress" if provider == "dbip" else "ip"
    if public_ip(data.get(field)) != address:
        raise QueryFailure("invalid_response")
    if provider == "ipinfo":
        facts.update(country_code=country(data.get("country_code")), asn=as_number(data.get("asn")), organization=text(data.get("as_name")))
    elif provider == "dbip":
        facts["country_code"] = country(data.get("countryCode"))
    elif provider == "ipregistry":
        connection, location, security = (mapping(data.get(k)) for k in ("connection", "location", "security"))
        facts.update(country_code=country(mapping(location.get("country")).get("code")), asn=number(connection.get("asn"), integer=True), organization=text(connection.get("organization")), network_type=text(connection.get("type")))
        for target, name in (("vpn", "is_vpn"), ("proxy", "is_proxy"), ("tor", "is_tor"), ("hosting", "is_cloud_provider"), ("recent_abuse", "is_abuser")):
            facts["flags"][target] = flag(security.get(name))
    elif provider == "ip2location":
        asn = data.get("asn")
        if isinstance(asn, str) and asn.isdigit():
            asn = int(asn)
        facts.update(country_code=country(data.get("country_code")), asn=number(asn, integer=True), organization=text(data.get("as")))
        facts["flags"]["proxy"] = flag(data.get("is_proxy"))
        proxy = mapping(data.get("proxy"))
        for target, name in (("vpn", "is_vpn"), ("tor", "is_tor"), ("hosting", "is_data_center")):
            facts["flags"][target] = flag(proxy.get(name))
        value = number(data.get("fraud_score"), 99)
        if value is not None:
            facts["scores"].append(dict(name="ip2location_fraud", value=value, scale=99, scope="ip_query"))
    return facts, "official_api"


SCORES = {key: {} for key in SPECS}
SCORES.update(ip2location={"ip2location_fraud": (99, "ip_query")})
for _key in ("scamalytics", "scamalytics-us"):
    SCORES[_key] = {"scamalytics_score": (100, "ip_query")}
