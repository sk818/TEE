/**
 * Color mapping utilities
 */

export enum ColormapType {
    Binary = 0,
    Viridis = 1,
    Grayscale = 2
}

/**
 * Viridis colormap (approximation)
 */
export function viridis(t: number): [number, number, number] {
    // Clamp to [0, 1]
    t = Math.max(0, Math.min(1, t));

    const c0 = [0.267004, 0.004874, 0.329415];
    const c1 = [0.127568, 0.566949, 0.550556];
    const c2 = [0.993248, 0.906157, 0.143936];

    const t2 = t * t;

    // Linear interpolation
    const mix = (a: number[], b: number[], t: number) =>
        a.map((v, i) => v + (b[i] - v) * t);

    const temp = mix(c0, c1, t);
    const final = mix(temp, c2, t2);

    return [
        Math.floor(final[0] * 255),
        Math.floor(final[1] * 255),
        Math.floor(final[2] * 255)
    ];
}

/**
 * Grayscale colormap
 */
export function grayscale(t: number): [number, number, number] {
    const val = Math.floor(t * 255);
    return [val, val, val];
}

/**
 * Binary colormap (yellow)
 */
export function binary(): [number, number, number] {
    return [255, 215, 0]; // Gold/yellow
}
