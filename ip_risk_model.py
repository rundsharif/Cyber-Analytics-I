from typing import Optional, Dict, Any

# You can make this more advanced later (ASN, dynamic lists, etc.)
COUNTRY_BASELINE_RISK = {
    # example: raise scores for high abuse-rate regions you observe in your data
    # "RU": 0.65, "CN": 0.60, "BR": 0.55, ...
}

def ip_risk_score(geo: Dict[str, Any]) -> float:
    """
    Returns a simple 0..1 risk score based on available geo info.
    You can tune these rules as you learn from data.
    """
    if not geo or not geo.get("origin_ip"):
        return 0.50  # unknown = neutral mid-risk

    cc = geo.get("origin_country_code")
    base = COUNTRY_BASELINE_RISK.get(cc, 0.40)  # default low baseline

    # If we failed to resolve lat/lon, bump uncertainty a bit
    if geo.get("origin_lat") is None or geo.get("origin_lon") is None:
        base = max(base, 0.50)

    return float(min(max(base, 0.0), 1.0))