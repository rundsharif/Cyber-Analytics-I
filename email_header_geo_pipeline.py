# email_header_geo_pipeline.py
"""
Single-email pipeline that:
  1) Parses headers from raw .eml bytes
  2) Scores them with the header-origin model
  3) Enriches with GeoIP from the Received: chain
  4) Returns a compact JSON-serializable dict for S3/Tableau.
"""

from __future__ import annotations
from typing import Optional, Dict, Any

from eml_header_extractor import extract_headers_from_eml_bytes
from header_origin_predict import score_header_features
from geo_enrich import enrich_headers_with_geo  # we alias this below


def process_single_eml_bytes(
    raw_eml_bytes: bytes,
    email_id_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Core pipeline used by local batch script and (later) Lambda.

    Returns a dict like:

    {
        "email_id": "...",
        "subject": "...",
        "header_trust_score": 0.63,
        "origin_ip": "...",
        "origin_country_code": "US",
        "origin_lat": 37.751,
        "origin_lon": -97.822
    }
    """

    # 1) Parse the EML into headers + engineered features
    parsed = extract_headers_from_eml_bytes(raw_eml_bytes)
    # parsed should contain:
    #   email_id, raw_headers, header_features, subject

    if email_id_override is not None:
        parsed["email_id"] = email_id_override

    email_id = parsed.get("email_id")
    subject = parsed.get("subject")
    header_features = parsed["header_features"]
    raw_headers = parsed["raw_headers"]

    # 2) Header-origin model score
    # score_header_features is the helper we used in header_origin_predict.py
    header_result = score_header_features(header_features)

    # It may return a float or a dict; normalize to float
    if isinstance(header_result, dict):
        header_trust_score = float(header_result.get("header_trust_score", 0.0))
    else:
        header_trust_score = float(header_result)

    # 3) Geo enrichment from the raw header string
    geo = enrich_headers_with_geo(raw_headers)
    # geo should contain: origin_ip, origin_country_code, origin_lat, origin_lon

    # 4) Compact record for S3/Tableau
    return {
        "email_id": email_id,
        "subject": subject,
        "header_trust_score": header_trust_score,
        "origin_ip": geo.get("origin_ip"),
        "origin_country_code": geo.get("origin_country_code"),
        "origin_lat": geo.get("origin_lat"),
        "origin_lon": geo.get("origin_lon"),
    }