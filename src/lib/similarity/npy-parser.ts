/**
 * NPY file parser - reads NumPy binary format files.
 *
 * NPY format specification:
 * - Bytes 0-5: Magic string "\x93NUMPY"
 * - Byte 6: Major version (1)
 * - Byte 7: Minor version (0)
 * - Bytes 8-9: Header length (little-endian uint16)
 * - Bytes 10+: Header (Python dict as string)
 * - Rest: Data (binary array)
 */

export function parseNPY(arrayBuffer: ArrayBuffer): Float32Array {
	const view = new DataView(arrayBuffer);

	// Check magic bytes
	const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2),
		view.getUint8(3), view.getUint8(4), view.getUint8(5));

	if (magic !== '\x93NUMPY') {
		throw new Error(`Invalid NPY file: magic bytes don't match. Got: ${JSON.stringify(magic)}`);
	}

	// Get version
	const majorVersion = view.getUint8(6);
	const minorVersion = view.getUint8(7);

	if (majorVersion !== 1) {
		throw new Error(`Unsupported NPY format version ${majorVersion}.${minorVersion}`);
	}

	// Get header length (little-endian uint16)
	const headerLen = view.getUint16(8, true);

	// Header is a Python dictionary as string (skip for now, just get to data)
	const dataStart = 10 + headerLen;

	// Calculate number of float32 values
	const byteLength = arrayBuffer.byteLength - dataStart;
	if (byteLength % 4 !== 0) {
		throw new Error(`Invalid NPY file: data length ${byteLength} is not divisible by 4`);
	}

	const numFloats = byteLength / 4;

	// Extract float32 data
	const result = new Float32Array(numFloats);
	const dataView = new DataView(arrayBuffer, dataStart);

	for (let i = 0; i < numFloats; i++) {
		result[i] = dataView.getFloat32(i * 4, true); // little-endian
	}

	return result;
}

/**
 * Parse NPY header to extract shape information.
 *
 * This is useful for understanding the dimensions of the array.
 *
 * @param arrayBuffer - The NPY file as ArrayBuffer
 * @returns Object with shape, dtype, and fortran_order
 */
export function parseNPYHeader(arrayBuffer: ArrayBuffer): {
	shape: number[];
	dtype: string;
	fortran_order: boolean;
} {
	const view = new DataView(arrayBuffer);

	// Check magic bytes
	const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2),
		view.getUint8(3), view.getUint8(4), view.getUint8(5));

	if (magic !== '\x93NUMPY') {
		throw new Error('Invalid NPY file');
	}

	// Get header length
	const headerLen = view.getUint16(8, true);

	// Extract header string
	const headerBytes = new Uint8Array(arrayBuffer, 10, headerLen);
	const headerStr = new TextDecoder().decode(headerBytes);

	// Parse header dictionary
	// Expected format: "{'descr': '<f4', 'fortran_order': False, 'shape': (height, width, dims), }"
	const shapeMatch = headerStr.match(/['"]shape['"]\s*:\s*\(([^)]+)\)/);
	const dtypeMatch = headerStr.match(/['"]descr['"]\s*:\s*['"]([^'"]+)['"]/);
	const fortranMatch = headerStr.match(/['"]fortran_order['"]\s*:\s*(True|False)/);

	if (!shapeMatch || !dtypeMatch) {
		throw new Error('Could not parse NPY header');
	}

	// Parse shape tuple
	const shapeStr = shapeMatch[1].trim();
	const shape = shapeStr.split(',')
		.map((s: string) => {
			const num = parseInt(s.trim(), 10);
			return isNaN(num) ? 1 : num; // Handle trailing comma
		})
		.filter((n: number) => n > 0);

	return {
		shape,
		dtype: dtypeMatch[1],
		fortran_order: fortranMatch ? fortranMatch[1] === 'True' : false
	};
}

/**
 * Convert shape and dtype to expected array size and type info.
 *
 * @param shape - Shape tuple from header
 * @param dtype - Data type string
 * @returns Object with totalElements and bytesPerElement
 */
export function getArrayInfo(shape: number[], dtype: string): {
	totalElements: number;
	bytesPerElement: number;
	expectedBytes: number;
} {
	let bytesPerElement = 4; // Default to float32

	if (dtype.includes('f4') || dtype.includes('float32')) {
		bytesPerElement = 4;
	} else if (dtype.includes('f8') || dtype.includes('float64')) {
		bytesPerElement = 8;
	} else if (dtype.includes('i4') || dtype.includes('int32')) {
		bytesPerElement = 4;
	} else if (dtype.includes('i8') || dtype.includes('int64')) {
		bytesPerElement = 8;
	} else if (dtype.includes('u1') || dtype.includes('uint8')) {
		bytesPerElement = 1;
	}

	const totalElements = shape.reduce((a, b) => a * b, 1);
	const expectedBytes = totalElements * bytesPerElement;

	return { totalElements, bytesPerElement, expectedBytes };
}
