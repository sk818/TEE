/**
 * WebGPU initialization and context management
 */

export class WebGPUContext {
    device!: GPUDevice;
    adapter!: GPUAdapter;

    async initialize(): Promise<boolean> {
        if (!navigator.gpu) {
            console.error('WebGPU not supported');
            return false;
        }

        try {
            this.adapter = await navigator.gpu.requestAdapter({
                powerPreference: 'high-performance'
            }) as GPUAdapter;

            if (!this.adapter) {
                console.error('Failed to get GPU adapter');
                return false;
            }

            this.device = await this.adapter.requestDevice({
                requiredLimits: {
                    maxStorageBufferBindingSize: 2 * 1024 * 1024 * 1024, // 2GB
                    maxBufferSize: 2 * 1024 * 1024 * 1024
                }
            });

            console.log('WebGPU initialized successfully');
            return true;
        } catch (error) {
            console.error('WebGPU initialization failed:', error);
            return false;
        }
    }

    createBuffer(size: number, usage: GPUBufferUsageFlags): GPUBuffer {
        return this.device.createBuffer({
            size,
            usage,
            mappedAtCreation: false
        });
    }

    createStorageBuffer(data: Float32Array | Uint32Array): GPUBuffer {
        const buffer = this.createBuffer(
            data.byteLength,
            GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST
        );

        this.device.queue.writeBuffer(buffer, 0, data);
        return buffer;
    }

    createUniformBuffer(data: Float32Array | Uint32Array): GPUBuffer {
        const buffer = this.createBuffer(
            data.byteLength,
            GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST
        );

        this.device.queue.writeBuffer(buffer, 0, data);
        return buffer;
    }
}
