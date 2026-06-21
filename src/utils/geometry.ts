import { CRYOSTAT_CONFIG } from '@/types';
import type { CryostatGeometry } from '@/types';

export function generateCryostatProfile(config: CryostatGeometry = CRYOSTAT_CONFIG): number[][][] {
  const { outerRadius, innerRadius, height, slices, rings } = config;
  const profiles: number[][][] = [];
  
  const cutAngle = 0;
  
  for (let ring = 0; ring <= rings; ring++) {
    const profile: number[][] = [];
    const radius = innerRadius + (outerRadius - innerRadius) * (ring / rings);
    
    for (let slice = 0; slice <= slices; slice++) {
      const angle = (slice / slices) * Math.PI * 2;
      
      if (angle > cutAngle && angle < cutAngle + Math.PI * 1.5) {
        const y = height / 2;
        profile.push([
          radius * Math.cos(angle),
          y,
          radius * Math.sin(angle)
        ]);
        profile.push([
          radius * Math.cos(angle),
          -y,
          radius * Math.sin(angle)
        ]);
      }
    }
    
    if (profile.length > 0) {
      profiles.push(profile);
    }
  }
  
  for (let ring = 0; ring <= rings; ring++) {
    const profile: number[][] = [];
    const radius = innerRadius + (outerRadius - innerRadius) * (ring / rings);
    
    for (let slice = 0; slice <= slices; slice++) {
      const angle = (slice / slices) * Math.PI * 2;
      
      if (angle > cutAngle && angle < cutAngle + Math.PI * 1.5) {
        const y = -height / 2;
        profile.push([
          radius * Math.cos(angle),
          y,
          radius * Math.sin(angle)
        ]);
      }
    }
    
    if (profile.length > 0) {
      profiles.push(profile);
    }
  }
  
  return profiles;
}

export function generateCutSurface(config: CryostatGeometry = CRYOSTAT_CONFIG): number[][][] {
  const { outerRadius, innerRadius, height, rings } = config;
  const surfaces: number[][][] = [];
  
  for (let ring = 0; ring <= rings; ring++) {
    const radius = innerRadius + (outerRadius - innerRadius) * (ring / rings);
    const surface: number[][] = [];
    
    for (let i = 0; i <= 20; i++) {
      const t = i / 20;
      const y = -height / 2 + t * height;
      surface.push([radius, y, 0]);
    }
    
    surfaces.push(surface);
  }
  
  for (let i = 0; i <= 20; i++) {
    const t = i / 20;
    const y = -height / 2 + t * height;
    const line: number[][] = [];
    
    for (let ring = 0; ring <= rings; ring++) {
      const radius = innerRadius + (outerRadius - innerRadius) * (ring / rings);
      line.push([radius, y, 0]);
    }
    
    surfaces.push(line);
  }
  
  return surfaces;
}

export function generateBottomSurface(config: CryostatGeometry = CRYOSTAT_CONFIG): number[][][] {
  const { outerRadius, innerRadius, slices, rings } = config;
  const y = -config.height / 2;
  const surfaces: number[][][] = [];
  
  for (let ring = 0; ring <= rings; ring++) {
    const radius = innerRadius + (outerRadius - innerRadius) * (ring / rings);
    const circle: number[][] = [];
    
    for (let slice = 0; slice <= slices; slice++) {
      const angle = (slice / slices) * Math.PI * 2;
      if (angle > 0 && angle < Math.PI * 1.5) {
        circle.push([
          radius * Math.cos(angle),
          y,
          radius * Math.sin(angle)
        ]);
      }
    }
    
    if (circle.length > 0) {
      surfaces.push(circle);
    }
  }
  
  for (let slice = 0; slice <= slices; slice++) {
    const angle = (slice / slices) * Math.PI * 2;
    if (angle > 0 && angle < Math.PI * 1.5) {
      const line: number[][] = [];
      
      for (let ring = 0; ring <= rings; ring++) {
        const radius = innerRadius + (outerRadius - innerRadius) * (ring / rings);
        line.push([
          radius * Math.cos(angle),
          y,
          radius * Math.sin(angle)
        ]);
      }
      
      surfaces.push(line);
    }
  }
  
  return surfaces;
}

export function generateSensorPositions(sensors: { position: [number, number, number] }[]): number[][] {
  return sensors.map(s => s.position);
}

export function normalizeValue(value: number, min: number, max: number): number {
  return Math.max(0, Math.min(1, (value - min) / (max - min)));
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function distance(p1: [number, number, number], p2: [number, number, number]): number {
  const dx = p1[0] - p2[0];
  const dy = p1[1] - p2[1];
  const dz = p1[2] - p2[2];
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

export function generateHeatMapTexture(
  width: number,
  height: number,
  hotspots: { position: [number, number]; intensity: number }[]
): Uint8ClampedArray {
  const data = new Uint8ClampedArray(width * height * 4);
  
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let intensity = 0;
      
      for (const hotspot of hotspots) {
        const dx = x / width - hotspot.position[0];
        const dy = y / height - hotspot.position[1];
        const dist = Math.sqrt(dx * dx + dy * dy);
        intensity += hotspot.intensity * Math.exp(-dist * 5);
      }
      
      intensity = Math.min(1, intensity);
      
      const idx = (y * width + x) * 4;
      data[idx] = Math.floor(0 + intensity * 255);
      data[idx + 1] = Math.floor(212 - intensity * 100);
      data[idx + 2] = Math.floor(255 - intensity * 200);
      data[idx + 3] = Math.floor(100 + intensity * 100);
    }
  }
  
  return data;
}
