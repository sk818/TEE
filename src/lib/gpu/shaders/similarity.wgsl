// Compute cosine similarity between query pixel and all pixels
// Input: normalized embeddings (float16 represented as float32 in shader)
// Output: similarity scores (float32)

struct Uniforms {
    width: u32,
    height: u32,
    embedding_dims: u32,
    query_x: u32,
    query_y: u32,
}

@group(0) @binding(0) var<uniform> uniforms: Uniforms;
@group(0) @binding(1) var<storage, read> embeddings: array<f32>;  // All embeddings
@group(0) @binding(2) var<storage, read_write> similarities: array<f32>;  // Output

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let x = global_id.x;
    let y = global_id.y;

    // Bounds check
    if (x >= uniforms.width || y >= uniforms.height) {
        return;
    }

    let pixel_idx = y * uniforms.width + x;
    let query_idx = uniforms.query_y * uniforms.width + uniforms.query_x;

    // Compute dot product (cosine similarity for normalized vectors)
    var dot_product: f32 = 0.0;

    for (var i: u32 = 0u; i < uniforms.embedding_dims; i = i + 1u) {
        let pixel_offset = pixel_idx * uniforms.embedding_dims + i;
        let query_offset = query_idx * uniforms.embedding_dims + i;

        dot_product = dot_product +
                     embeddings[pixel_offset] * embeddings[query_offset];
    }

    // Store result
    similarities[pixel_idx] = dot_product;
}
