#!/usr/bin/env node
/**
 * Manual-labelling classified-pixel export (Louis Driver).
 *
 * labels.js::computeManualClassification() is the shared nearest-centroid
 * classification behind both the Panel 5 overlay and the new "Classified
 * pixels (not points)" export option: every viewport pixel is assigned to
 * a class by polygon interiors first, then threshold-gated
 * nearest-centroid. classifiedPixelFeatures() then groups those pixels per
 * class for vectorisation (d3-contour, not exercised here).
 *
 * This checks the assignment logic directly (no d3 needed): two class
 * centroids, points clustered near each, with a threshold that includes
 * the near points and excludes the far ones.
 *
 * Run:  node validation/test_classified_pixel_export.mjs
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', 'public', 'js', 'labels.js'), 'utf8');

function extract(name) {
    let i = src.indexOf(`function ${name}(`);
    if (i === -1) throw new Error(`function not found in labels.js: ${name}`);
    let depth = 0, started = false, j = i;
    while (true) {
        const c = src[j];
        if (c === '{') { depth++; started = true; }
        else if (c === '}') { depth--; if (started && depth === 0) return src.slice(i, j + 1); }
        j++;
    }
}

let passed = 0, failed = 0;
const ok = (c, m) => { if (c) passed++; else { failed++; console.log(`  FAIL: ${m}`); } };

// --- synthetic viewport: dim=2, two clusters --------------------------
const dim = 2;
// classes: "A" centroid (0,0), "B" centroid (10,10)
const pts = [
    [0.1, 0.0],   // near A
    [-0.1, 0.2],  // near A
    [10.1, 9.9],  // near B
    [9.8, 10.1],  // near B
    [5.0, 5.0],   // between -> outside both thresholds (dist ~7.07 > 2)
];
const N = pts.length;
const values = new Float32Array(N * dim);
const coords = new Int32Array(N * 2);
pts.forEach((p, i) => {
    values[i * dim] = p[0];
    values[i * dim + 1] = p[1];
    coords[i * 2] = i;       // gx
    coords[i * 2 + 1] = 0;   // gy
});

globalThis.window = globalThis;
window.localVectors = {
    dim, numVectors: N, values, coords,
    metadata: { geotransform: { a: 1, c: 0, e: 1, f: 0 } },
};
window.getDequant = () => ({ scale: new Array(dim).fill(1), min: new Array(dim).fill(0) });

const manualLabels = [
    { name: 'A', color: '#ff0000', visible: true, type: 'point', embedding: [0, 0], threshold: 2 },
    { name: 'B', color: '#0000ff', visible: true, type: 'point', embedding: [10, 10], threshold: 2 },
];

const api = new Function(
    'manualLabels', 'rasterizePolygon',
    extract('computeManualClassification') + '\nreturn computeManualClassification;'
)(manualLabels, () => []);

const cls = api();
ok(cls !== null, 'returns a classification');
ok(JSON.stringify(cls.classNames) === JSON.stringify(['A', 'B']), 'class names in label order');
const a = Array.from(cls.assignments);
ok(a[0] === 0 && a[1] === 0, 'points near A -> class 0');
ok(a[2] === 1 && a[3] === 1, 'points near B -> class 1');
ok(a[4] === -1, 'point between the clusters is left unassigned (outside both thresholds)');

// threshold 0 -> that class contributes nothing
const noThresh = new Function(
    'manualLabels', 'rasterizePolygon',
    extract('computeManualClassification') + '\nreturn computeManualClassification;'
)([{ ...manualLabels[0], threshold: 0 }, manualLabels[1]], () => []);
const a2 = Array.from(noThresh().assignments);
ok(a2[0] === -1 && a2[1] === -1, 'class A with threshold 0 assigns nothing');
ok(a2[2] === 1 && a2[3] === 1, 'class B still assigns its near points');

// no active labels -> null
const none = new Function(
    'manualLabels', 'rasterizePolygon',
    extract('computeManualClassification') + '\nreturn computeManualClassification;'
)([], () => []);
ok(none() === null, 'no visible labels with embeddings -> null');

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
