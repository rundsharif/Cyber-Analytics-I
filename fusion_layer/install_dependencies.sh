#!/usr/bin/env bash
set -e

echo "========================================="
echo "Fusion Layer - Dependency Installation"
echo "========================================="
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not in PATH."
    echo "Please install Python 3.8 or later before running this script."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Detected Python version: $PYTHON_VERSION"
echo ""

# Upgrade pip
echo "Upgrading pip..."
python3 -m pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing fusion layer dependencies from requirements.txt..."
python3 -m pip install -r requirements.txt

echo ""
echo "========================================="
echo "Installation complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Review MACHINE_SETUP_AND_RUN_STEPS.txt for deployment instructions"
echo "2. Configure the three model-output locations in config/fusion_config.yaml"
echo "3. Run: python3 run_integrated_fusion.py"
echo ""