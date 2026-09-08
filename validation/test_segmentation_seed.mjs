#!/usr/bin/env node
/**
 * Auto-label k-means is seeded (Keshav, 2026-09-08).
 *
 * segmentation.js gained a `seed` (default 42, exposed as #seg-seed-input):
 *   - mulberry32(seed)      tiny deterministic PRNG
 *   - buildSample(N, size, rand)   Fisher-Yates subsample now takes an RNG
 *   - the worker blob embeds a copy of mulberry32 and uses it for
 *     K-means++ init + empty-cluster re-seed (checked here by string, the
 *     Web Worker itself isn't exercised)
 *
 * Same seed + k + vectors => identical clusters; different seed => a
 * different subsample. Guards that no bare Math.random() is left in the
 * k-means path.
 *
 * Run:  node validation/test_segmentation_seed.mjs
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(__dirname, '..', 'public', 'js', 'segmentation.js'), 'utf8');

function extract(name) {
    let i = src.indexOf(`function ${name}(`);
    if (i === -1) throw new Error(`function not found in segmentation.js: ${name}`);
    if (src.slice(i - 6, i) === 'async ') i -= 6;
    let depth = 0, started = false, j = i;
    while (true) {
        const c = src[j];
        if (c === '{') { depth++; started = true; }
        else if (c === '}') { depth--; if (started && depth === 0) return src.slice(i, j + 1); }
        j++;
    }
}

const api = new Function(
    extract('mulberry32') + '\n' +
    extract('buildSample') + '\n' +
    'return { mulberry32, buildSample };'
)();

let passed = 0, failed = 0;
const ok = (c, m) => { if (c) passed++; else { failed++; console.log(`  FAIL: ${m}`); } };

// --- mulberry32 is deterministic and in [0, 1) ----------------------
{
    const a = api.mulberry32(42);
    const b = api.mulberry32(42);
    const seqA = Array.from({ length: 8 }, () => a());
    const seqB = Array.from({ length: 8 }, () => b());
    ok(JSON.stringify(seqA) === JSON.stringify(seqB), 'same seed -> same sequence');
    ok(seqA.every(x => x >= 0 && x < 1), 'values in [0, 1)');
    const c = api.mulberry32(43);
    const seqC = Array.from({ length: 8 }, () => c());
    ok(JSON.stringify(seqA) !== JSON.stringify(seqC), 'different seed -> different sequence');
}

// --- buildSample: reproducible with a seeded RNG -------------------
{
    const N = 5000, size = 500;
    const s1 = api.buildSample(N, size, api.mulberry32(42));
    const s2 = api.buildSample(N, size, api.mulberry32(42));
    const s3 = api.buildSample(N, size, api.mulberry32(7));
    ok(s1.length === size, 'sample has the requested size');
    ok(Array.from(s1).every(v => v >= 0 && v < N), 'indices in range');
    ok(Array.from(s1).join(',') === Array.from(s2).join(','), 'seed 42 -> identical sample');
    ok(Array.from(s1).join(',') !== Array.from(s3).join(','), 'seed 7 -> different sample');
    ok(new Set(s1).size === size, 'sample has no duplicates');
}

// --- the k-means path no longer calls bare Math.random() ----------
{
    // Everything from the worker blob through runKMeans must use the
    // seeded `rand()` / a passed-in RNG instead.
    const kmeansRegion = src.slice(src.indexOf('K-means Worker'), src.indexOf('Segmentation Overlay'));
    ok(!/Math\.random\(/.test(kmeansRegion), 'no bare Math.random() in the k-means worker + runKMeans');
    ok(/\$\{mulberry32\.toString\(\)\}/.test(src), 'worker blob embeds mulberry32');
    ok(/seed: seed >>> 0/.test(src), 'runKMeans posts the seed to the worker');
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
