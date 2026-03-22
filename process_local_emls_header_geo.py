# process_local_emls_header_geo.py
# Run header-origin + GeoIP on all .eml files in local_emls/
# and write compact JSON outputs to local_output_header_geo/

from pathlib import Path
import json
from typing import Optional, Dict

from eml_header_extractor import extract_header_features_from_eml
from header_origin_predict import predict_header_trust
from geo_enrich import enrich_headers_with_geo

IN_DIR = Path("local_emls")
OUT_DIR = Path("local_output_header_geo")


def process_single_eml_bytes(raw_eml_bytes, email_id_override=None):
    """
    Minimal per-email pipeline:
      1) parse headers into features
      2) score header trust
      3) geo-enrich origin IP
      4) return compact dict shaped like the end_to_end test
    """

    parsed = extract_header_features_from_eml(raw_eml_bytes)
    # parsed contains: email_id, raw_headers, header_features, subject

    if email_id_override is not None:
        parsed["email_id"] = email_id_override

    email_id = parsed.get("email_id")
    subject = parsed.get("subject")
    header_features = parsed["header_features"]
    raw_headers = parsed["raw_headers"]

    # Header-origin score (same as test_end_to_end.py)
    header_result = predict_header_trust(header_features)
    if isinstance(header_result, dict):
        header_trust_score = float(header_result.get("header_trust_score", 0.0))
    else:
        header_trust_score = float(header_result)

    # Geo enrichment
    geo = enrich_headers_with_geo(raw_headers)

    return {
        "email_id": email_id,
        "subject": subject,
        "header_trust_score": header_trust_score,
        "origin_ip": geo.get("origin_ip"),
        "origin_country_code": geo.get("origin_country_code"),
        "origin_lat": geo.get("origin_lat"),
        "origin_lon": geo.get("origin_lon"),
    }


def main():
    OUT_DIR.mkdir(exist_ok=True)

    eml_files = sorted(IN_DIR.glob("*.eml"))
    if not eml_files:
        print(f"[WARN] No .eml files found in {IN_DIR.resolve()}")
        return

    print(f"[INFO] Found {len(eml_files)} .eml files in {IN_DIR}/")

    for eml_path in eml_files:
        print(f"[INFO] Processing {eml_path.name} ...")
        raw_eml = eml_path.read_bytes()

        result = process_single_eml_bytes(raw_eml, email_id_override=eml_path.name)

        out_path = OUT_DIR / f"{eml_path.stem}.json"
        out_path.write_text(json.dumps(result, indent=2))
        print(f"[INFO] Wrote {out_path}")


if __name__ == "__main__":
    main()