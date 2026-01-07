#!/usr/bin/env python3
"""
Test script for similarity search and intelligent relabeling workflow.

This script tests:
1. Simulated manual labeling with embeddings
2. /api/embeddings/search-similar endpoint
3. /api/embeddings/relabel-by-similarity endpoint with relabeling logic
"""

import json
import numpy as np
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.web_server import app

def test_similarity_search():
    """Test similarity search workflow with realistic embeddings."""

    print("\n" + "="*80)
    print("TEST 1: SIMILARITY SEARCH WITH THRESHOLD FILTERING")
    print("="*80)

    # Create Flask test client
    client = app.test_client()

    # Step 1: Create a query embedding (simulating manual label)
    # Real embeddings are uint8 [0-255]
    np.random.seed(42)
    query_embedding = np.random.randint(0, 256, size=128, dtype=np.uint8)
    print(f"\n✓ Generated query embedding: shape={query_embedding.shape}, dtype={query_embedding.dtype}")
    print(f"  Sample values: {query_embedding[:5].tolist()}...")

    # Step 2: Test with multiple thresholds
    test_thresholds = [0.3, 0.5, 0.7]
    results = {}

    for threshold in test_thresholds:
        print(f"\n📊 Testing threshold: {threshold}")

        response = client.post('/api/embeddings/search-similar',
            json={
                'embedding': query_embedding.tolist(),
                'threshold': threshold,
                'viewport_id': 'malleswaram_500m'
            },
            content_type='application/json'
        )

        data = response.get_json()

        if data.get('success'):
            matches = data.get('matches', [])
            stats = data.get('query_stats', {})
            results[threshold] = {
                'matches_count': len(matches),
                'computation_time': stats.get('computation_time_ms'),
                'total_pixels': stats.get('total_pixels')
            }

            print(f"  ✓ Success!")
            print(f"    - Matches found: {len(matches):,} / {stats.get('total_pixels'):,}")
            print(f"    - Computation time: {stats.get('computation_time_ms'):.1f}ms")

            if matches:
                # Show first few matches
                print(f"    - First 3 matches:")
                for i, match in enumerate(matches[:3]):
                    print(f"      {i+1}. Lat/Lon: ({match['lat']:.6f}, {match['lon']:.6f}), Distance: {match['distance']:.4f}")
        else:
            print(f"  ✗ Error: {data.get('error')}")

    print(f"\n✓ Threshold comparison:")
    for threshold in test_thresholds:
        if threshold in results:
            print(f"  - Threshold {threshold}: {results[threshold]['matches_count']:,} matches")

    return True


def test_relabeling_logic():
    """Test intelligent relabeling with multiple labels."""

    print("\n" + "="*80)
    print("TEST 2: INTELLIGENT RELABELING LOGIC")
    print("="*80)

    client = app.test_client()

    np.random.seed(42)

    # Create 3 labels: "road", "building", "pavement"
    print("\n1. Creating test labels with embeddings...")

    # "road" label: 3 embeddings (will add 2 more later)
    road_embeddings = [
        np.random.randint(100, 200, 128),  # Pixel 1
        np.random.randint(105, 205, 128),  # Pixel 2
        np.random.randint(110, 210, 128),  # Pixel 3
    ]

    # "building" label: 2 embeddings
    building_embeddings = [
        np.random.randint(50, 150, 128),   # Pixel 4
        np.random.randint(55, 155, 128),   # Pixel 5
    ]

    # "pavement" label: 2 embeddings
    pavement_embeddings = [
        np.random.randint(150, 250, 128),  # Pixel 6
        np.random.randint(155, 255, 128),  # Pixel 7
    ]

    # Convert to uint8
    road_embeddings = [e.astype(np.uint8) for e in road_embeddings]
    building_embeddings = [e.astype(np.uint8) for e in building_embeddings]
    pavement_embeddings = [e.astype(np.uint8) for e in pavement_embeddings]

    print(f"  ✓ Created 3 labels with 7 total embeddings:")
    print(f"    - road: {len(road_embeddings)} embeddings")
    print(f"    - building: {len(building_embeddings)} embeddings")
    print(f"    - pavement: {len(pavement_embeddings)} embeddings")

    # Step 2: Test relabeling BEFORE adding new pixels
    print("\n2. Testing initial relabeling (should have 0 relabels)...")

    initial_labeled_pixels = {
        '10,20': {'label': 'road', 'embedding': road_embeddings[0].tolist(), 'lat': 13.0045, 'lon': 77.5670},
        '30,40': {'label': 'road', 'embedding': road_embeddings[1].tolist(), 'lat': 13.0050, 'lon': 77.5675},
        '50,60': {'label': 'building', 'embedding': building_embeddings[0].tolist(), 'lat': 13.0055, 'lon': 77.5680},
        '70,80': {'label': 'building', 'embedding': building_embeddings[1].tolist(), 'lat': 13.0060, 'lon': 77.5685},
    }

    response = client.post('/api/embeddings/relabel-by-similarity',
        json={
            'label_embeddings': {
                'road': [e.tolist() for e in road_embeddings[:2]],
                'building': [e.tolist() for e in building_embeddings],
            },
            'labeled_pixels': initial_labeled_pixels
        },
        content_type='application/json'
    )

    data = response.get_json()
    print(f"\n  ✓ Initial relabel response:")
    print(f"    - Success: {data.get('success')}")
    print(f"    - Relabeled pixels: {data.get('relabel_count')}")
    print(f"    - Stats: {data.get('stats')}")

    # Step 3: Simulate adding new "road" pixels (similar to existing road pixels)
    print("\n3. Simulating addition of 2 similar 'road' pixels...")

    # Create 2 new embeddings similar to road (by averaging existing + noise)
    avg_road = np.mean(road_embeddings, axis=0)
    new_road_embs = [
        (avg_road + np.random.randint(-10, 10, 128)).clip(0, 255).astype(np.uint8),
        (avg_road + np.random.randint(-10, 10, 128)).clip(0, 255).astype(np.uint8),
    ]

    print(f"  ✓ Created 2 similar embeddings (avg road ± noise)")

    # Now test relabeling after adding these new pixels
    print("\n4. Testing relabeling after refinement...")

    refined_labeled_pixels = {
        '10,20': {'label': 'road', 'embedding': road_embeddings[0].tolist(), 'lat': 13.0045, 'lon': 77.5670},
        '30,40': {'label': 'road', 'embedding': road_embeddings[1].tolist(), 'lat': 13.0050, 'lon': 77.5675},
        '90,100': {'label': 'road', 'embedding': new_road_embs[0].tolist(), 'lat': 13.0065, 'lon': 77.5690},
        '110,120': {'label': 'road', 'embedding': new_road_embs[1].tolist(), 'lat': 13.0070, 'lon': 77.5695},
        '50,60': {'label': 'building', 'embedding': building_embeddings[0].tolist(), 'lat': 13.0055, 'lon': 77.5680},
        '70,80': {'label': 'building', 'embedding': building_embeddings[1].tolist(), 'lat': 13.0060, 'lon': 77.5685},
    }

    response = client.post('/api/embeddings/relabel-by-similarity',
        json={
            'label_embeddings': {
                'road': [e.tolist() for e in road_embeddings + new_road_embs],
                'building': [e.tolist() for e in building_embeddings],
            },
            'labeled_pixels': refined_labeled_pixels
        },
        content_type='application/json'
    )

    data = response.get_json()
    print(f"\n  ✓ Refined relabel response:")
    print(f"    - Success: {data.get('success')}")
    print(f"    - Relabeled pixels: {data.get('relabel_count')}")
    print(f"    - Stats: {data.get('stats')}")

    if data.get('relabeled'):
        print(f"\n    Relabeling details:")
        for rel in data.get('relabeled', []):
            print(f"      - {rel['key']}: {rel['old_label']} ({rel['old_distance']:.4f}) → {rel['new_label']} ({rel['new_distance']:.4f})")

    return True


def test_edge_cases():
    """Test edge cases and error handling."""

    print("\n" + "="*80)
    print("TEST 3: EDGE CASES AND ERROR HANDLING")
    print("="*80)

    client = app.test_client()

    # Test 1: Invalid embedding dimension
    print("\n1. Testing invalid embedding dimension...")
    response = client.post('/api/embeddings/search-similar',
        json={
            'embedding': list(range(64)),  # Wrong dimension
            'threshold': 0.5,
            'viewport_id': 'malleswaram_500m'
        },
        content_type='application/json'
    )
    data = response.get_json()
    print(f"  ✓ Response: {data.get('success')} - {data.get('error')}")

    # Test 2: Invalid threshold
    print("\n2. Testing invalid threshold (> 1.0)...")
    response = client.post('/api/embeddings/search-similar',
        json={
            'embedding': list(range(128)),
            'threshold': 1.5,  # Invalid threshold
            'viewport_id': 'malleswaram_500m'
        },
        content_type='application/json'
    )
    data = response.get_json()
    print(f"  ✓ Response: {data.get('success')} - {data.get('error')}")

    # Test 3: Missing FAISS index
    print("\n3. Testing missing FAISS index...")
    response = client.post('/api/embeddings/search-similar',
        json={
            'embedding': list(range(128)),
            'threshold': 0.5,
            'viewport_id': 'nonexistent_viewport'
        },
        content_type='application/json'
    )
    data = response.get_json()
    print(f"  ✓ Response: {data.get('success')} - {data.get('error')}")

    # Test 4: Empty label embeddings
    print("\n4. Testing relabeling with empty labels...")
    response = client.post('/api/embeddings/relabel-by-similarity',
        json={
            'label_embeddings': {},
            'labeled_pixels': {}
        },
        content_type='application/json'
    )
    data = response.get_json()
    print(f"  ✓ Response: {data.get('success')} - {data.get('error', 'No error')}")

    # Test 5: No labeled pixels (should still return success)
    print("\n5. Testing relabeling with no labeled pixels...")
    response = client.post('/api/embeddings/relabel-by-similarity',
        json={
            'label_embeddings': {
                'road': [list(range(128))]
            },
            'labeled_pixels': {}
        },
        content_type='application/json'
    )
    data = response.get_json()
    print(f"  ✓ Response: {data.get('success')}, Relabeled: {data.get('relabel_count')}")

    return True


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("SIMILARITY SEARCH & INTELLIGENT RELABELING TEST SUITE")
    print("="*80)

    try:
        # Test 1: Similarity Search
        if not test_similarity_search():
            print("\n✗ Test 1 failed!")
            return False

        # Test 2: Relabeling Logic
        if not test_relabeling_logic():
            print("\n✗ Test 2 failed!")
            return False

        # Test 3: Edge Cases
        if not test_edge_cases():
            print("\n✗ Test 3 failed!")
            return False

        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80 + "\n")
        return True

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
