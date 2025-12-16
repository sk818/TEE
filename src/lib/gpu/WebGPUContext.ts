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

            // Try to get device with reasonable limits
            // Different browsers have different limits - start conservative
            const limitsToTry = [
                {
                    maxStorageBufferBindingSize: 256 * 1024 * 1024, // 256MB
                    maxBufferSize: 256 * 1024 * 1024
                },
                {
                    maxStorageBufferBindingSize: 128 * 1024 * 1024, // 128MB
                    maxBufferSize: 128 * 1024 * 1024
                }
            ];

            let deviceCreated = false;
            for (const limits of limitsToTry) {
                try {
                    this.device = await this.adapter.requestDevice({
                        requiredLimits: limits
                    });
                    console.log(`✅ Device created with limits: ${limits.maxStorageBufferBindingSize / (1024 * 1024)}MB`);
                    deviceCreated = true;
                    break;
                } catch (e) {
                    console.warn(`Could not create device with ${limits.maxStorageBufferBindingSize / (1024 * 1024)}MB limits, trying smaller...`);
                }
            }

            if (!deviceCreated) {
                // Last resort: request device without explicit limits
                console.warn('Requesting device without explicit buffer limits...');
                this.device = await this.adapter.requestDevice();
            }

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
