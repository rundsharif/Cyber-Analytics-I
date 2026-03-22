#!/bin/bash
set -e

rm -rf layer_python
mkdir -p layer_python/python

echo "[*] Installing Lambda dependencies (without boto3, botocore)..."

pip3 install \
    requests \
    python-dateutil \
    --target layer_python/python

echo "[*] Zipping layer..."
cd layer_python
zip -r9 ../lambda_deps_layer.zip .
cd ..

echo "[*] Done. Upload lambda_deps_layer.zip to Lambda Layers."