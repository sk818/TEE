/**
 * Manage cosine similarity computation on GPU
 */

import { WebGPUContext } from './WebGPUContext';
import similarityShader from './shaders/similarity.wgsl?raw';
import thresholdShader from './shaders/threshold.wgsl?raw';

export interface ComputeParams {
    queryX: number;
    queryY: number;
    threshold: number;
    colormapId: number;
}

export class SimilarityCompute {
    private context: WebGPUContext;
    private similarityPipeline!: GPUComputePipeline;
    private thresholdPipeline!: GPUComputePipeline;

    // Buffers
    private embeddingsBuffer!: GPUBuffer;
    private similaritiesBuffer!: GPUBuffer;
    private colorsBuffer!: GPUBuffer;
    private uniformsBuffer!: GPUBuffer;

    // Bind groups
    private similarityBindGroup!: GPUBindGroup;
    private thresholdBindGroup!: GPUBindGroup;

    private width: number;
    private height: number;
    private embeddingDims: number;

    constructor(context: WebGPUContext, width: number, height: number, dims: number) {
        this.context = context;
        this.width = width;
        this.height = height;
        this.embeddingDims = dims;
    }

    async initialize(embeddings: Float32Array): Promise<void> {
        // Create compute pipelines
        await this.createPipelines();

        // Create buffers
        this.createBuffers(embeddings);

        // Create bind groups
        this.createBindGroups();
    }

    private async createPipelines(): Promise<void> {
        // Similarity compute pipeline
        const similarityModule = this.context.device.createShaderModule({
            code: similarityShader
        });

        this.similarityPipeline = this.context.device.createComputePipeline({
            layout: 'auto',
            compute: {
                module: similarityModule,
                entryPoint: 'main'
            }
        });

        // Threshold filter pipeline
        const thresholdModule = this.context.device.createShaderModule({
            code: thresholdShader
        });

        this.thresholdPipeline = this.context.device.createComputePipeline({
            layout: 'auto',
            compute: {
                module: thresholdModule,
                entryPoint: 'main'
            }
        });
    }

    private createBuffers(embeddings: Float32Array): void {
        const numPixels = this.width * this.height;

        // Embeddings buffer (read-only)
        this.embeddingsBuffer = this.context.createStorageBuffer(embeddings);

        // Similarities buffer (read-write)
        this.similaritiesBuffer = this.context.createBuffer(
            numPixels * 4, // float32
            GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC
        );

        // Colors buffer (output)
        this.colorsBuffer = this.context.createBuffer(
            numPixels * 16, // vec4<f32>
            GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC
        );

        // Uniforms buffer
        const uniformsData = new Uint32Array([
            this.width,
            this.height,
            this.embeddingDims,
            0, // query_x (will be updated)
            0  // query_y (will be updated)
        ]);
        this.uniformsBuffer = this.context.createUniformBuffer(uniformsData);
    }

    private createBindGroups(): void {
        // Similarity computation bind group
        this.similarityBindGroup = this.context.device.createBindGroup({
            layout: this.similarityPipeline.getBindGroupLayout(0),
            entries: [
                { binding: 0, resource: { buffer: this.uniformsBuffer } },
                { binding: 1, resource: { buffer: this.embeddingsBuffer } },
                { binding: 2, resource: { buffer: this.similaritiesBuffer } }
            ]
        });

        // Threshold filter bind group
        this.thresholdBindGroup = this.context.device.createBindGroup({
            layout: this.thresholdPipeline.getBindGroupLayout(0),
            entries: [
                { binding: 0, resource: { buffer: this.uniformsBuffer } },
                { binding: 1, resource: { buffer: this.similaritiesBuffer } },
                { binding: 2, resource: { buffer: this.colorsBuffer } }
            ]
        });
    }

    async compute(params: ComputeParams): Promise<Float32Array> {
        // Update uniforms
        const uniformsData = new Uint32Array([
            this.width,
            this.height,
            this.embeddingDims,
            params.queryX,
            params.queryY
        ]);
        this.context.device.queue.writeBuffer(this.uniformsBuffer, 0, uniformsData);

        // Create command encoder
        const commandEncoder = this.context.device.createCommandEncoder();

        // Pass 1: Compute similarities
        const similarityPass = commandEncoder.beginComputePass();
        similarityPass.setPipeline(this.similarityPipeline);
        similarityPass.setBindGroup(0, this.similarityBindGroup);

        const workgroupsX = Math.ceil(this.width / 16);
        const workgroupsY = Math.ceil(this.height / 16);
        similarityPass.dispatchWorkgroups(workgroupsX, workgroupsY);
        similarityPass.end();

        // Pass 2: Apply threshold and colormap
        const thresholdData = new Float32Array([
            this.width,
            this.height,
            params.threshold,
            params.colormapId
        ]);
        this.context.device.queue.writeBuffer(this.uniformsBuffer, 0, thresholdData);

        const thresholdPass = commandEncoder.beginComputePass();
        thresholdPass.setPipeline(this.thresholdPipeline);
        thresholdPass.setBindGroup(0, this.thresholdBindGroup);
        thresholdPass.dispatchWorkgroups(workgroupsX, workgroupsY);
        thresholdPass.end();

        // Copy results to staging buffer
        const stagingBuffer = this.context.createBuffer(
            this.width * this.height * 16,
            GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ
        );

        commandEncoder.copyBufferToBuffer(
            this.colorsBuffer, 0,
            stagingBuffer, 0,
            stagingBuffer.size
        );

        // Submit commands
        this.context.device.queue.submit([commandEncoder.finish()]);

        // Read results
        await stagingBuffer.mapAsync(GPUMapMode.READ);
        const result = new Float32Array(stagingBuffer.getMappedRange()).slice();
        stagingBuffer.unmap();

        return result;
    }

    destroy(): void {
        this.embeddingsBuffer?.destroy();
        this.similaritiesBuffer?.destroy();
        this.colorsBuffer?.destroy();
        this.uniformsBuffer?.destroy();
    }
}
