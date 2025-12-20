#!/bin/bash

# TEE Preprocessing Pipeline
# Generates and processes test embeddings through the full pipeline

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║    TESSERA EMBEDDING EXPLORER - PREPROCESSING PIPELINE         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Activate venv if it exists
if [ -d "venv" ]; then
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
fi

# Parameters
VIEWPORT_BOUNDS="-0.5 51.5 0.5 52.5"  # Cambridge area
YEARS="2017 2018 2019 2020 2021 2022 2023 2024"
DATA_DIR="data"
RAW_EMBEDDINGS_DIR="$DATA_DIR/raw_embeddings"
PROCESSED_EMBEDDINGS_DIR="public/data/embeddings"

echo ""
echo "📋 Configuration:"
echo "  Viewport bounds (lon/lat): $VIEWPORT_BOUNDS"
echo "  Years: $YEARS"
echo "  Raw data directory: $RAW_EMBEDDINGS_DIR"
echo "  Output directory: $PROCESSED_EMBEDDINGS_DIR"
echo ""

# Step 1: Generate test data
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Generating synthetic test embeddings..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 preprocessing/generate_test_data.py \
    --width 256 \
    --height 256 \
    --dimensions 128 \
    --years $YEARS \
    --output "$RAW_EMBEDDINGS_DIR"

echo ""

# Step 2: Prepare embeddings
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Processing embeddings (normalize, convert to binary)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 preprocessing/prepare_embeddings.py \
    --input "$RAW_EMBEDDINGS_DIR" \
    --output "$PROCESSED_EMBEDDINGS_DIR" \
    --bounds $VIEWPORT_BOUNDS

echo ""

# Step 3: Compute PCA
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Computing PCA for visualization..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 preprocessing/compute_pca.py \
    --input "$PROCESSED_EMBEDDINGS_DIR" \
    --output "$PROCESSED_EMBEDDINGS_DIR/pca_features.bin" \
    --bounds $VIEWPORT_BOUNDS \
    --years $YEARS

echo ""

# Final summary
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                   PIPELINE COMPLETE! ✅                         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Output files:"
ls -lh "$PROCESSED_EMBEDDINGS_DIR" 2>/dev/null || echo "  (no files found)"
echo ""
echo "🚀 Next steps:"
echo "  1. Refresh your browser at http://localhost:3000/"
echo "  2. The application should now load with embedding data"
echo ""
echo "📈 Data summary:"
echo "  - Embeddings: 256x256 pixels, 128 dimensions"
echo "  - Years: 2017-2024 (8 years)"
echo "  - Location: Cambridge, UK vicinity"
echo ""
