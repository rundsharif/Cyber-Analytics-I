import os
import json
import boto3

from eml_header_extractor import extract_header_features_from_eml
from header_origin_predict import predict_header_trust
from geo_enrich import enrich_headers_with_geo
from ip_risk_model import score_ip_risk  # adjust if your function name is different

s3 = boto3.client("s3")

# Bucket where we write processed results
PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "email-analytics-processed")


def _get_object_bytes(bucket: str, key: str) -> bytes:
    resp = s3.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


def _put_json(bucket: str, key: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )


def lambda_handler(event, context):
    """
    Triggered by S3 ObjectCreated events on email-ingestion-raw-data for *.eml files.
    """
    results = []

    for record in event.get("Records", []):
        src_bucket = record["s3"]["bucket"]["name"]
        src_key = record["s3"]["object"]["key"]

        # Ignore anything that is not an EML file
        if not src_key.lower().endswith(".eml"):
            continue

        # 1) Download EML from S3
        raw_eml = _get_object_bytes(src_bucket, src_key)

        # 2) Extract header features and context
        parsed = extract_header_features_from_eml(raw_eml)
        header_feats = parsed["header_features"]

        # 3) Run header origin model
        header_trust = float(predict_header_trust(header_feats))

        # 4) Geo enrichment from Received headers
        geo = enrich_headers_with_geo(parsed["raw_headers"])

        # 5) IP risk model
        origin_ip = geo.get("origin_ip")
        ip_risk = float(score_ip_risk(origin_ip)) if origin_ip else None

        # 6) Build output record
        out = {
            "email_id": parsed["email_id"],
            "source_bucket": src_bucket,
            "source_key": src_key,
            "subject": parsed["subject"],
            "header_trust_score": header_trust,
            "origin_ip": origin_ip,
            "origin_country_code": geo.get("origin_country_code"),
            "origin_country_name": geo.get("origin_country_name"),
            "origin_city": geo.get("origin_city"),
            "origin_lat": geo.get("origin_lat"),
            "origin_lon": geo.get("origin_lon"),
            "ip_risk_score": ip_risk,
        }

        # Mirror the source key under header_geo_ip/, but swap .eml for .json
        # e.g. rundebeepbeep@gmail.com/foo/bar.eml -> header_geo_ip/rundebeepbeep@gmail.com/foo/bar.json
        dest_key = f"header_geo_ip/{src_key.rsplit('.', 1)[0]}.json"

        _put_json(PROCESSED_BUCKET, dest_key, out)
        results.append({"email_id": parsed["email_id"], "dest_key": dest_key})

    return {
        "statusCode": 200,
        "processed": len(results),
        "results": results,
    }