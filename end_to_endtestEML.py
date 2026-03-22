import json
from header_origin_predict import predict_header_trust
from geo_enrich import enrich_headers_with_geo
from eml_header_extractor import extract_header_features_from_eml

with open("sample.eml", "rb") as f:
    raw = f.read()

parsed = extract_header_features_from_eml(raw)
header_score = predict_header_trust(parsed["header_features"])
geo = enrich_headers_with_geo(parsed["raw_headers"])

output = {
    "email_id": parsed["email_id"],
    "subject": parsed["subject"],
    "header_trust_score": header_score,
    "origin_ip": geo.get("origin_ip"),
    "origin_country_code": geo.get("origin_country_code"),
    "origin_lat": geo.get("origin_lat"),
    "origin_lon": geo.get("origin_lon")
}

print(json.dumps(output, indent=4))