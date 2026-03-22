import os
import sys
import json

from header_origin_predict import predict_header_trust
from geo_enrich import enrich_headers_with_geo
from eml_header_extractor import extract_header_features_from_eml


def main():
    print("=== Header Origin + GeoIP end-to-end test ===")

    # 1) Pick input file
    if len(sys.argv) > 1:
        eml_path = sys.argv[1]
    else:
        eml_path = "sample.eml"  # default

    print(f"[INFO] Using EML file: {eml_path}")

    if not os.path.exists(eml_path):
        print(f"[ERROR] File not found: {eml_path}")
        print("       Put a .eml file in the project folder or pass a path, e.g.:")
        print("       python3 test_end_to_end.py path/to/email.eml")
        return

    # 2) Read raw EML
    with open(eml_path, "rb") as f:
        raw_bytes = f.read()
    print(f"[INFO] Loaded {len(raw_bytes)} bytes from {eml_path}")

    # 3) Extract header features
    parsed = extract_header_features_from_eml(raw_bytes)
    print("[INFO] Parsed keys:", list(parsed.keys()))
    print("[INFO] Header feature keys:", list(parsed["header_features"].keys()))

    # 4) Run header origin model
    header_score = predict_header_trust(parsed["header_features"])
    print(f"[INFO] Header trust score from model: {header_score:.4f}")

    # 5) Run GeoIP enrichment
    geo = enrich_headers_with_geo(parsed["raw_headers"])
    print("[INFO] Geo enrichment result:", geo)

    # 6) Build final record for downstream / Tableau
    output = {
        "email_id": parsed["email_id"],
        "subject": parsed["subject"],
        "header_trust_score": float(header_score),
        "origin_ip": geo.get("origin_ip"),
        "origin_country_code": geo.get("origin_country_code"),
        "origin_lat": geo.get("origin_lat"),
        "origin_lon": geo.get("origin_lon"),
    }

    print("\n=== Final combined JSON ===")
    print(json.dumps(output, indent=4))
    print("=== End of test ===")


if __name__ == "__main__":
    main()