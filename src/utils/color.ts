import { COLORS } from '@/types';

export function temperatureToColor(temp: number, minTemp: number = 77, maxTemp: number = 120): [number, number, number, number] {
  const normalized = Math.max(0, Math.min(1, (temp - minTemp) / (maxTemp - minTemp)));
  
  const r = Math.floor(0 + normalized * 255);
  const g = Math.floor(212 - normalized * 100);
  const b = Math.floor(255 - normalized * 200);
  
  return [r, g, b, 255];
}

export function temperatureToHex(temp: number, minTemp: number = 77, maxTemp: number = 120): string {
  const [r, g, b] = temperatureToColor(temp, minTemp, maxTemp);
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

export function createGradient(colors: string[], stops: number[]): (value: number) => string {
  return (value: number) => {
    const clamped = Math.max(0, Math.min(1, value));
    for (let i = 0; i < stops.length - 1; i++) {
      if (clamped >= stops[i] && clamped <= stops[i + 1]) {
        const t = (clamped - stops[i]) / (stops[i + 1] - stops[i]);
        return interpolateColor(colors[i], colors[i + 1], t);
      }
    }
    return colors[colors.length - 1];
  };
}

function interpolateColor(color1: string, color2: string, t: number): string {
  const r1 = parseInt(color1.slice(1, 3), 16);
  const g1 = parseInt(color1.slice(3, 5), 16);
  const b1 = parseInt(color1.slice(5, 7), 16);
  
  const r2 = parseInt(color2.slice(1, 3), 16);
  const g2 = parseInt(color2.slice(3, 5), 16);
  const b2 = parseInt(color2.slice(5, 7), 16);
  
  const r = Math.round(r1 + (r2 - r1) * t);
  const g = Math.round(g1 + (g2 - g1) * t);
  const b = Math.round(b1 + (b2 - b1) * t);
  
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

export function hexToRgba(hex: string, alpha: number = 1): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export const resistivityGradient = createGradient(
  ['#00d4ff', '#00ffd5', '#ffa502', '#ff4757'],
  [0, 0.3, 0.7, 1]
);

export function getSensorColor(index: number): string {
  const colors = [
    COLORS.primary, COLORS.secondary, COLORS.accent, '#ffa502',
    '#ff6b81', '#2ed573', COLORS.danger, '#eccc68',
    '#a29bfe', '#fd79a8', '#00b894', '#fdcb6e',
    '#e17055', '#0984e3', '#6c5ce7', '#00cec9',
    '#fab1a0', '#81ecec', '#dfe6e9', '#b2bec3',
    '#fd79a8', '#a29bfe', '#ffeaa7', '#dfe6e9'
  ];
  return colors[index % colors.length];
}
