# lambda_header_geo.py
# S3 -> header + geo pipeline -> S3 (processed JSON)

import os
import json
import boto3

from process_local_emls_header_geo import process_single_eml_bytes

s3 = boto3.client("s3")

RAW_BUCKET = os.environ.get("RAW_BUCKET", "email-ingestion-raw-data")
PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "email-analytics-processed")
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "header_geo/")

def lambda_handler(event, context):
    """
    Triggered by S3 PUT on the raw-email bucket.
    For each .eml object:
      - download from raw bucket
      - run header+geo pipeline
      - upload JSON to processed bucket
    """
    print("[INFO] Event:", json.dumps(event))

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        # Only handle .eml files (skip folders or other extensions)
        if not key.lower().endswith(".eml"):
            print(f"[INFO] Skipping non-eml object: {key}")
            continue

        print(f"[INFO] Processing S3 object s3://{bucket}/{key}")

        # 1) Download raw .eml bytes
        obj = s3.get_object(Bucket=bucket, Key=key)
        raw_eml = obj["Body"].read()

        # Use filename as email_id
        email_id = key.split("/")[-1]

        # 2) Run your existing pipeline
        result = process_single_eml_bytes(raw_eml, email_id_override=email_id)

        # 3) Choose output key in processed bucket
        #    e.g. header_geo/testing_upload/sample.json
        #    (preserve the folder structure before the file name if you want)
        prefix_part = "/".join(key.split("/")[:-1])  # everything before filename
        if prefix_part:
            out_key = f"{OUTPUT_PREFIX}{prefix_part}/{email_id}.json"
        else:
            out_key = f"{OUTPUT_PREFIX}{email_id}.json"

        body = json.dumps(result).encode("utf-8")

        # 4) Upload JSON
        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=out_key,
            Body=body,
            ContentType="application/json",
        )

        print(f"[INFO] Wrote processed JSON to s3://{PROCESSED_BUCKET}/{out_key}")

    return {"status": "ok"}