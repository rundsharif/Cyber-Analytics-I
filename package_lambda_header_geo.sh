#!/usr/bin/env bash
set -e

# --- Config ---
ZIP_NAME="lambda_header_geo_bundle.zip"
BUILD_DIR="lambda_build"

# Clean any old build
rm -rf "$BUILD_DIR" "$ZIP_NAME"
mkdir -p "$BUILD_DIR"

echo "[*] Using Python: $(python3 --version)"

# --- Install deps into build dir ---
echo "[*] Installing Python dependencies into $BUILD_DIR ..."
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install \
  --target "$BUILD_DIR" \
  boto3 geoip2 scikit-learn joblib >/dev/null

# --- Copy your project files that Lambda needs ---
echo "[*] Copying project files into $BUILD_DIR ..."

cp \
  lambda_header_geo.py \
  process_local_emls_header_geo.py \
  eml_header_extractor.py \
  header_origin_predict.py \
  geo_enrich.py \
  header_origin_trec_model.pkl \
  header_origin_trec_columns.pkl \
  GeoLite2-City.mmdb \
  "$BUILD_DIR"

# If your lambda file is named lambda_header_geo_ip.py instead,
# comment the lambda_header_geo.py line above and uncomment this:
# cp lambda_header_geo_ip.py "$BUILD_DIR/lambda_header_geo.py"

# --- Create the zip ---
echo "[*] Creating zip $ZIP_NAME ..."
(
  cd "$BUILD_DIR"
  zip -r "../$ZIP_NAME" . >/dev/null
)

echo "[*] Done."
echo "Created: $ZIP_NAME"
echo "Upload this zip to the Lambda function (handler: lambda_header_geo.lambda_handler)."