import { temperatureToColor } from './color';

export const PARTICLE_STRIDE = 10;
// [0:3] position x,y,z (Float32)
// [3:6] velocity x,y,z (Float32)
// [6]   size (Float32)
// [7]   opacity (Float32)
// [8]   temperature (Float32)
// [9]   id (Uint32, mapped from Float32)

export interface PoolStatistics {
  activeCount: number;
  capacity: number;
  allocatedBytes: number;
}

export interface ParticlePoolAPI {
  getActiveCount(): number;
  getCapacity(): number;
  getStatistics(): PoolStatistics;
  getFloat32View(): Float32Array;
  reset(count: number): void;
  setParticle(index: number, position: [number, number, number], velocity: [number, number, number], size: number, opacity: number, temperature: number, id: number): void;
  updatePositionInPlace(index: number, position: [number, number, number]): void;
  updateTemperatureInPlace(index: number, temperature: number, opacity: number): void;
  advance(dt: number, boilingIntensity: number): void;
  toDeckGlFormat(): Array<any>;
  toDeckGlBinary(): {
    length: number;
    attributes: {
      getPosition: { value: Float32Array; size: number };
      getFillColor: { value: Uint8ClampedArray; size: number };
      getRadius: { value: Float32Array; size: number };
    };
  };
  dispose(): void;
}

export class ParticlePool implements ParticlePoolAPI {
  private capacity: number;
  private buffer: ArrayBuffer;
  private f32: Float32Array;
  private u32: Uint32Array;
  private activeCount: number = 0;

  constructor(maxParticles: number) {
    this.capacity = maxParticles;
    const bytes = maxParticles * PARTICLE_STRIDE * 4;
    this.buffer = new ArrayBuffer(bytes);
    this.f32 = new Float32Array(this.buffer);
    this.u32 = new Uint32Array(this.buffer);
  }

  getActiveCount(): number {
    return this.activeCount;
  }

  getCapacity(): number {
    return this.capacity;
  }

  getStatistics(): PoolStatistics {
    return {
      activeCount: this.activeCount,
      capacity: this.capacity,
      allocatedBytes: this.buffer.byteLength
    };
  }

  getFloat32View(): Float32Array {
    return this.f32;
  }

  reset(count: number): void {
    const clamped = Math.max(0, Math.min(count, this.capacity));
    this.activeCount = clamped;
  }

  setParticle(
    index: number,
    position: [number, number, number],
    velocity: [number, number, number],
    size: number,
    opacity: number,
    temperature: number,
    id: number
  ): void {
    if (index < 0 || index >= this.capacity) return;
    const base = index * PARTICLE_STRIDE;
    this.f32[base + 0] = position[0];
    this.f32[base + 1] = position[1];
    this.f32[base + 2] = position[2];
    this.f32[base + 3] = velocity[0];
    this.f32[base + 4] = velocity[1];
    this.f32[base + 5] = velocity[2];
    this.f32[base + 6] = size;
    this.f32[base + 7] = opacity;
    this.f32[base + 8] = temperature;
    this.u32[base + 9] = id;
  }

  updatePositionInPlace(
    index: number,
    position: [number, number, number]
  ): void {
    if (index < 0 || index >= this.activeCount) return;
    const base = index * PARTICLE_STRIDE;
    this.f32[base + 0] = position[0];
    this.f32[base + 1] = position[1];
    this.f32[base + 2] = position[2];
  }

  updateTemperatureInPlace(
    index: number,
    temperature: number,
    opacity: number
  ): void {
    if (index < 0 || index >= this.activeCount) return;
    const base = index * PARTICLE_STRIDE;
    this.f32[base + 8] = temperature;
    this.f32[base + 7] = opacity;
  }

  advance(dt: number, boilingIntensity: number): void {
    const n = this.activeCount;
    const riseSpeed = 0.5 + boilingIntensity * 2.0;
    const view = this.f32;
    for (let i = 0; i < n; i++) {
      const base = i * PARTICLE_STRIDE;
      view[base + 0] += view[base + 3] * dt * 60;
      view[base + 1] += view[base + 4] * dt * 60;
      view[base + 2] += view[base + 5] * dt * 60;

      const wobblePhase = (Date.now() / 300 + i * 0.1) % (Math.PI * 2);
      const wobble = Math.sin(wobblePhase) * 0.002;
      view[base + 0] += wobble;
      view[base + 2] -= wobble;

      if (view[base + 1] > 1.3) {
        view[base + 1] = -0.2;
        const angle = Math.random() * Math.PI * 2;
        const radius = 0.2 + Math.random() * 0.7;
        view[base + 0] = Math.cos(angle) * radius;
        view[base + 2] = Math.sin(angle) * radius;
      }

      const verticalNorm = Math.max(0, Math.min(1, (view[base + 1] + 0.2) / 1.5));
      view[base + 7] = Math.max(0, 1 - verticalNorm);
      view[base + 8] = 77 + verticalNorm * 12 + Math.random() * 3;
      view[base + 6] = 0.01 + Math.random() * 0.02 * (1 + boilingIntensity);
    }
  }

  toDeckGlFormat(): Array<any> {
    const result = new Array(this.activeCount);
    const view = this.f32;
    const ids = this.u32;
    for (let i = 0; i < this.activeCount; i++) {
      const base = i * PARTICLE_STRIDE;
      const t = view[base + 8];
      result[i] = {
        position: [view[base + 0], view[base + 1], view[base + 2]],
        temperature: t,
        size: view[base + 6],
        opacity: view[base + 7],
        _color: temperatureToColor(t),
        _id: ids[base + 9]
      };
    }
    return result;
  }

  toDeckGlBinary(): {
    length: number;
    attributes: {
      getPosition: { value: Float32Array; size: number };
      getFillColor: { value: Uint8ClampedArray; size: number };
      getRadius: { value: Float32Array; size: number };
    };
  } {
    const n = this.activeCount;
    const positions = new Float32Array(n * 3);
    const colors = new Uint8ClampedArray(n * 4);
    const radii = new Float32Array(n);
    const view = this.f32;

    for (let i = 0; i < n; i++) {
      const base = i * PARTICLE_STRIDE;
      const pBase = i * 3;
      positions[pBase + 0] = view[base + 0];
      positions[pBase + 1] = view[base + 1];
      positions[pBase + 2] = view[base + 2];

      const t = view[base + 8];
      const c = temperatureToColor(t);
      const cBase = i * 4;
      colors[cBase + 0] = c[0];
      colors[cBase + 1] = c[1];
      colors[cBase + 2] = c[2];
      colors[cBase + 3] = Math.floor(view[base + 7] * c[3]);

      radii[i] = view[base + 6] * 50;
    }

    return {
      length: n,
      attributes: {
        getPosition: { value: positions, size: 3 },
        getFillColor: { value: colors, size: 4 },
        getRadius: { value: radii, size: 1 }
      }
    };
  }

  dispose(): void {
    (this.buffer as any) = null;
    (this.f32 as any) = null;
    (this.u32 as any) = null;
  }
}
