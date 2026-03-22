#!/bin/bash
set -e

rm -rf lambda_build
mkdir -p lambda_build

echo "[*] Copying minimal Lambda code..."

# ONLY COPY THESE 4 FILES
cp lambda_header_geo.py lambda_build/
cp eml_header_extractor.py lambda_build/
cp header_origin_predict.py lambda_build/
cp ip_risk_model.py lambda_build/

echo "[*] Creating deployment zip..."

cd lambda_build
zip -r ../lambda_header_geo_bundle.zip .
cd ..

echo "[*] Done! Upload lambda_header_geo_bundle.zip to Lambda."