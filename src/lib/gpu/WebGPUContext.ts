/**
 * WebGPU initialization and context management
 */

export class WebGPUContext {
    device!: GPUDevice;
    adapter!: GPUAdapter;

    async initialize(): Promise<boolean> {
        // Check WebGPU availability
        if (!navigator.gpu) {
            console.error('WebGPU not available on this browser');
            console.warn('For Safari 18.3, enable WebGPU in Settings > Develop > Experimental Features');
            console.warn('For Chrome/Edge: Update to version 113+');
            return false;
        }

        try {
            console.log('Requesting WebGPU adapter...');

            this.adapter = await navigator.gpu.requestAdapter({
                powerPreference: 'high-performance'
            }) as GPUAdapter;

            if (!this.adapter) {
                console.error('Failed to get GPU adapter - no compatible GPU found');
                console.warn('Try a different power preference or check GPU drivers');
                return false;
            }

            console.log('WebGPU adapter obtained, requesting device...');

            this.device = await this.adapter.requestDevice({
                requiredLimits: {
                    maxStorageBufferBindingSize: 2 * 1024 * 1024 * 1024, // 2GB
                    maxBufferSize: 2 * 1024 * 1024 * 1024
                }
            });

            console.log('✅ WebGPU initialized successfully');
            console.log(`GPU: ${this.adapter.name || 'Unknown'}`);
            return true;
        } catch (error) {
            console.error('❌ WebGPU initialization failed:', error);
            if (error instanceof Error) {
                console.error('Error details:', error.message);
            }
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
