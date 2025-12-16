// Apply threshold to similarity scores for visualization
// Input: similarity scores
// Output: RGBA color values

struct Uniforms {
    width: u32,
    height: u32,
    threshold: f32,
    colormap_id: u32,  // 0=binary, 1=viridis, 2=magma
}

@group(0) @binding(0) var<uniform> uniforms: Uniforms;
@group(0) @binding(1) var<storage, read> similarities: array<f32>;
@group(0) @binding(2) var<storage, read_write> colors: array<vec4<f32>>;

// Viridis colormap approximation
fn viridis(t: f32) -> vec3<f32> {
    let c0 = vec3<f32>(0.267004, 0.004874, 0.329415);
    let c1 = vec3<f32>(0.127568, 0.566949, 0.550556);
    let c2 = vec3<f32>(0.993248, 0.906157, 0.143936);

    let t2 = t * t;
    return mix(mix(c0, c1, t), c2, t2);
}

@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let x = global_id.x;
    let y = global_id.y;

    if (x >= uniforms.width || y >= uniforms.height) {
        return;
    }

    let idx = y * uniforms.width + x;
    let similarity = similarities[idx];

    var color: vec4<f32>;

    if (similarity < uniforms.threshold) {
        // Below threshold: transparent
        color = vec4<f32>(0.0, 0.0, 0.0, 0.0);
    } else {
        // Above threshold: apply colormap
        let normalized = (similarity - uniforms.threshold) / (1.0 - uniforms.threshold);

        if (uniforms.colormap_id == 0u) {
            // Binary: yellow highlight
            color = vec4<f32>(1.0, 0.843, 0.0, 0.8);
        } else if (uniforms.colormap_id == 1u) {
            // Viridis
            let rgb = viridis(normalized);
            color = vec4<f32>(rgb, 0.8);
        } else {
            // Default: grayscale
            color = vec4<f32>(normalized, normalized, normalized, 0.8);
        }
    }

    colors[idx] = color;
}
