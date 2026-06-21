export interface SensorData {
  timestamp: number;
  sensorId: string;
  currentDensity: number;
  temperature: number;
  magneticField: number;
  resistivity: number;
}

export interface SensorInfo {
  sensorId: string;
  position: [number, number, number];
  type: string;
  channel: number;
}

export interface SummaryStats {
  timestamp: number;
  avgCurrentDensity: number;
  maxCurrentDensity: number;
  avgTemperature: number;
  maxTemperature: number;
  avgMagneticField: number;
  avgResistivity: number;
  quenchDetected: boolean;
  quenchSensors: string[];
}

export interface ParticleState {
  id: number;
  position: [number, number, number];
  velocity: [number, number, number];
  size: number;
  opacity: number;
  temperature: number;
}

export interface ParticleResponse {
  particles: ParticleState[];
  timestamp: number;
  heatZoneTemperature: number;
}

export interface TimeRange {
  startTime: number;
  endTime: number;
}

export interface QuenchEvent {
  sensorId: string;
  startTime: number;
  peakResistivity: number;
  peakTemperature: number;
}

export interface GlobalState {
  currentTime: number;
  isPlaying: boolean;
  playbackSpeed: number;
  quenchDetected: boolean;
}

export interface CryostatGeometry {
  outerRadius: number;
  innerRadius: number;
  height: number;
  slices: number;
  rings: number;
}

export const CRYOSTAT_CONFIG: CryostatGeometry = {
  outerRadius: 1.2,
  innerRadius: 0.9,
  height: 2.0,
  slices: 64,
  rings: 16
};

export const COLORS = {
  background: '#0a1628',
  primary: '#00d4ff',
  secondary: '#00ffd5',
  accent: '#7b68ee',
  warning: '#ffa502',
  danger: '#ff4757',
  success: '#2ed573',
  text: '#ffffff',
  textSecondary: '#a0aec0',
  glass: 'rgba(10, 22, 40, 0.7)',
  glassBorder: 'rgba(0, 212, 255, 0.3)'
};

export const SENSOR_COLORS = [
  '#00d4ff', '#00ffd5', '#7b68ee', '#ffa502',
  '#ff6b81', '#2ed573', '#ff4757', '#eccc68',
  '#a29bfe', '#fd79a8', '#00b894', '#fdcb6e',
  '#e17055', '#0984e3', '#6c5ce7', '#00cec9',
  '#fab1a0', '#81ecec', '#dfe6e9', '#b2bec3',
  '#fd79a8', '#a29bfe', '#ffeaa7', '#dfe6e9'
];

export const FONTS = {
  display: '"Orbitron", monospace',
  mono: '"JetBrains Mono", monospace'
};
