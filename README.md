# TESSERA Embedding Explorer (TEE)

An interactive web-based viewer for exploring TESSERA embeddings, Sentinel-2 composites, and OpenStreetMap data over a 20km × 20km viewport with real-time cosine similarity clustering and multi-temporal analysis.

## Features

- **Interactive Viewport Selection**: Select any 20km × 20km region on a world map
- **Real-time Similarity Computing**: GPU-accelerated cosine similarity using WebGPU
- **Multi-temporal Analysis**: Explore embeddings from 2017-2024
- **Visual Similarity Search**: Click on any pixel to find similar locations
- **Dynamic Threshold Control**: Adjust sensitivity in real-time
- **Location Search**: Find locations by name using Nominatim
- **Preset Locations**: Quick access to study areas

## Technology Stack

- **Frontend**: Svelte 4
- **GPU Compute**: WebGPU with WGSL compute shaders
- **Visualization**: Deck.gl with WebGL2
- **Mapping**: MapLibre GL JS
- **Build Tool**: Vite
- **Language**: TypeScript

## Project Structure

```
tessera-explorer/
├── preprocessing/           # Python data preprocessing scripts
│   ├── download_data.py
│   ├── prepare_embeddings.py
│   ├── prepare_sentinel2.py
│   ├── compute_pca.py
│   └── requirements.txt
├── public/
│   └── data/               # Data files served statically
│       ├── embeddings/
│       ├── sentinel2/
│       ├── pca/
│       └── osm/
├── src/
│   ├── lib/
│   │   ├── gpu/            # GPU compute context and shaders
│   │   │   ├── WebGPUContext.ts
│   │   │   ├── SimilarityCompute.ts
│   │   │   └── shaders/
│   │   │       ├── similarity.wgsl
│   │   │       └── threshold.wgsl
│   │   ├── data/           # Data loaders
│   │   │   ├── EmbeddingLoader.ts
│   │   │   ├── SentinelLoader.ts
│   │   │   └── DataTypes.ts
│   │   ├── layers/         # Deck.gl visualization layers
│   │   └── utils/          # Utility functions
│   │       ├── coordinates.ts
│   │       └── colormaps.ts
│   ├── components/         # Svelte components
│   │   ├── ViewportSelector.svelte
│   │   ├── ExplorerView.svelte
│   │   ├── ThresholdControl.svelte
│   │   ├── YearSelector.svelte
│   │   └── StatsPanel.svelte
│   ├── App.svelte
│   └── main.ts
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

## Installation

1. Clone the repository:
```bash
git clone <repo-url>
cd tessera-explorer
```

2. Install dependencies:
```bash
npm install
```

3. Prepare data (Python preprocessing):
```bash
cd preprocessing
pip install -r requirements.txt
python prepare_embeddings.py --input <path> --output ../public/data/embeddings --bounds <min_lon> <min_lat> <max_lon> <max_lat>
python compute_pca.py --input ../public/data/embeddings --output ../public/data/pca/pca.bin --bounds <min_lon> <min_lat> <max_lon> <max_lat>
```

## Development

Start the development server:
```bash
npm run dev
```

The application will be available at `http://localhost:3000`

## Building for Production

```bash
npm run build
npm run preview
```

## Browser Requirements

- **Chrome/Edge**: 113+ (WebGPU support)
- **Firefox**: Experimental (enable `dom.webgpu.enabled`)
- **Safari**: 17.4+ (WebGPU in Technology Preview)

## Performance Targets

- Initial load: < 3 seconds
- Click to similarity: < 10ms
- Threshold adjustment: < 1ms
- Year switching: < 50ms
- Render FPS: 60 FPS
- Memory usage: < 6GB

## Data Formats

### TESSERA Embeddings (Binary Format)
- **Magic**: "TESS" (4 bytes)
- **Header**: 64 bytes (version, year, dimensions, bounds)
- **Data**: float16, row-major order
- **Dimensions**: 128-dimensional embeddings (uint8 normalized to float16)

### Sentinel-2 Composites (Zarr Format)
- **Shape**: (years, quarters, height, width, bands)
- **Compression**: Blosc (zstd, level 5)
- **Value range**: 0-10000 (reflectance × 10000)

### PCA Components (Binary Format)
- **Magic**: "PCA3" (4 bytes)
- **Components**: 3 principal components for RGB
- **Data**: float32, normalized to 0-1

## Key Components

### ViewportSelector
Interactive world map interface for selecting a 20km × 20km study area.

**Features**:
- Click to place viewport center
- Drag to reposition (planned)
- Location search via Nominatim
- Preset study areas
- Data availability overlay

### ExplorerView
Main visualization interface showing embeddings and similarity results.

**Features**:
- Year selector (2017-2024)
- Threshold slider for similarity control
- Real-time statistics panel
- GPU-accelerated similarity computation

### GPU Compute Pipeline
Two-stage computation using WebGPU:

1. **Similarity Compute** (similarity.wgsl): Cosine similarity between query pixel and all pixels
2. **Threshold Filter** (threshold.wgsl): Apply threshold and colormap visualization

## Usage

1. **Select Viewport**:
   - Click on the map to place viewport center
   - Use search to find specific locations
   - Select from preset study areas

2. **Explore Embeddings**:
   - Select a year (2017-2024)
   - Click on any pixel to compute similarity
   - Adjust threshold slider to explore different similarity ranges

3. **Analyze Results**:
   - View statistics panel showing number of similar pixels
   - Observe similarity distribution visualization
   - Switch years to compare temporal changes

## Future Enhancements

- Export functionality (similarity masks, ROIs)
- Multi-pixel selection and comparison
- Temporal animation through years
- Advanced statistical tools
- Web Worker-based data streaming
- Mobile-optimized interface
- Additional colormaps
- Performance profiling tools

## Troubleshooting

### WebGPU Not Available
- Check browser version (Chrome 113+, Edge 113+, Safari 17.4+)
- Enable experimental features in browser flags
- Update GPU drivers
- Check if GPU is supported by your device

### Memory Issues
- Reduce viewport size to 15km × 15km
- Load fewer temporal snapshots
- Clear browser cache
- Use private browsing mode

### Slow Performance
- Check GPU utilization with browser DevTools
- Verify WebGPU shader compilation succeeds
- Profile JavaScript execution
- Ensure network is not the bottleneck

## Documentation

See the full technical specification for detailed implementation details, data formats, and architecture decisions.

## License

MIT

## Support

For questions and issues:
- Check the troubleshooting guide
- Review browser console for errors
- Verify data files are in correct format
- Ensure WebGPU is properly initialized

---

**Version**: 1.0.0
**Last Updated**: December 2024
