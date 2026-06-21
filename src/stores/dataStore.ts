import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import axios from 'axios';
import type {
  SensorData,
  SensorInfo,
  SummaryStats,
  ParticleState,
  TimeRange,
  QuenchEvent
} from '@/types';
import { ParticlePool } from '@/utils/particlePool';
import type { PoolStatistics, ParticlePoolAPI } from '@/utils/particlePool';

const API_BASE = 'http://localhost:8000/api';
const MAX_PARTICLES = 5000;
const SUMMARY_THROTTLE_MS = 200;
const PARTICLE_FETCH_THROTTLE_MS = 500;

export const useDataStore = defineStore('data', () => {
  const sensors = ref<SensorInfo[]>([]);
  const timeSeriesData = ref<SensorData[]>([]);
  const currentStats = ref<SummaryStats | null>(null);
  const particles = ref<ParticleState[]>([]);
  const timeRange = ref<TimeRange>({ startTime: 0, endTime: 600 });
  const currentTime = ref(0);
  const isPlaying = ref(false);
  const playbackSpeed = ref(1);
  const quenchEvents = ref<QuenchEvent[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const heatZoneTemperature = ref(77);

  const particlePool = ref<ParticlePoolAPI | null>(null);
  const lastSummaryFetch = ref(0);
  const lastParticleFetch = ref(0);
  const pendingFetch = ref<Promise<void> | null>(null);

  const quenchDetected = computed(() => currentStats.value?.quenchDetected ?? false);
  const activeSensors = computed(() => currentStats.value?.quenchSensors ?? []);
  const boilingIntensity = computed(() =>
    Math.max(0, Math.min(1, (heatZoneTemperature.value - 77) / 20))
  );

  function getParticlePool(): ParticlePoolAPI {
    if (!particlePool.value) {
      particlePool.value = new ParticlePool(MAX_PARTICLES) as ParticlePoolAPI;
    }
    return particlePool.value;
  }

  function getPoolStats(): PoolStatistics {
    return getParticlePool().getStatistics();
  }

  function snakeToCamel(obj: any): any {
    if (Array.isArray(obj)) {
      return obj.map(snakeToCamel);
    }
    if (obj !== null && typeof obj === 'object') {
      return Object.keys(obj).reduce((acc, key) => {
        const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
        acc[camelKey] = snakeToCamel(obj[key]);
        return acc;
      }, {} as any);
    }
    return obj;
  }

  async function fetchSensors() {
    try {
      const response = await axios.get(`${API_BASE}/sensors`);
      sensors.value = snakeToCamel(response.data);
    } catch (e) {
      error.value = 'Failed to fetch sensors';
      console.error(e);
    }
  }

  async function fetchTimeRange() {
    try {
      const response = await axios.get(`${API_BASE}/time-range`);
      const data = snakeToCamel(response.data);
      timeRange.value = data;
      currentTime.value = data.startTime;
    } catch (e) {
      error.value = 'Failed to fetch time range';
      console.error(e);
    }
  }

  async function fetchTimeSeries(startTime: number, endTime: number, sensorIds?: string[]) {
    try {
      isLoading.value = true;
      const params = new URLSearchParams({
        start_time: startTime.toString(),
        end_time: endTime.toString(),
        downsample: '10'
      });
      if (sensorIds?.length) {
        params.append('sensor_ids', sensorIds.join(','));
      }
      const response = await axios.get(`${API_BASE}/timeseries?${params.toString()}`);
      timeSeriesData.value = snakeToCamel(response.data.data);
    } catch (e) {
      error.value = 'Failed to fetch time series';
      console.error(e);
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchSummary(timestamp: number, force = false) {
    const now = Date.now();
    if (!force && now - lastSummaryFetch.value < SUMMARY_THROTTLE_MS) {
      return;
    }
    lastSummaryFetch.value = now;
    try {
      const response = await axios.get(`${API_BASE}/summary`, {
        params: { timestamp }
      });
      currentStats.value = snakeToCamel(response.data);
    } catch (e) {
      console.error('Failed to fetch summary:', e);
    }
  }

  function hydratePoolFromApi(apiParticles: ParticleState[]) {
    const pool = getParticlePool();
    const count = Math.min(apiParticles.length, MAX_PARTICLES);
    pool.reset(count);
    for (let i = 0; i < count; i++) {
      const p = apiParticles[i];
      pool.setParticle(
        i,
        p.position,
        p.velocity,
        p.size,
        p.opacity,
        p.temperature,
        p.id
      );
    }
  }

  async function fetchParticles(timestamp: number, numParticles: number = 2500, force = false) {
    const now = Date.now();
    if (!force && now - lastParticleFetch.value < PARTICLE_FETCH_THROTTLE_MS) {
      predictParticlesLocally(0.016);
      return;
    }
    lastParticleFetch.value = now;
    try {
      const response = await axios.get(`${API_BASE}/particles`, {
        params: { timestamp, num_particles: numParticles }
      });
      const data = snakeToCamel(response.data);
      particles.value = data.particles;
      heatZoneTemperature.value = data.heatZoneTemperature;
      hydratePoolFromApi(data.particles);
    } catch (e) {
      console.error('Failed to fetch particles:', e);
    }
  }

  function predictParticlesLocally(dt: number) {
    const pool = getParticlePool();
    if (pool.getActiveCount() === 0) return;
    pool.advance(dt, boilingIntensity.value);
  }

  function advanceParticles(dt: number) {
    predictParticlesLocally(dt);
  }

  async function fetchQuenchEvents(startTime: number, endTime: number) {
    try {
      const response = await axios.get(`${API_BASE}/quench-events`, {
        params: { start_time: startTime, end_time: endTime }
      });
      quenchEvents.value = snakeToCamel(response.data.events);
    } catch (e) {
      error.value = 'Failed to fetch quench events';
      console.error(e);
    }
  }

  function setCurrentTime(time: number) {
    currentTime.value = Math.max(
      timeRange.value.startTime,
      Math.min(timeRange.value.endTime, time)
    );
  }

  function togglePlayback() {
    isPlaying.value = !isPlaying.value;
  }

  function setPlaybackSpeed(speed: number) {
    playbackSpeed.value = Math.max(0.1, Math.min(10, speed));
  }

  function stepForward(seconds: number = 1) {
    setCurrentTime(currentTime.value + seconds);
    fetchSummary(currentTime.value, true);
    fetchParticles(currentTime.value, 2500, true);
  }

  function stepBackward(seconds: number = 1) {
    setCurrentTime(currentTime.value - seconds);
    fetchSummary(currentTime.value, true);
    fetchParticles(currentTime.value, 2500, true);
  }

  function seekTo(time: number) {
    setCurrentTime(time);
    fetchSummary(time, true);
    fetchParticles(time, 2500, true);
  }

  async function initialize() {
    getParticlePool();
    await Promise.all([
      fetchSensors(),
      fetchTimeRange()
    ]);
    if (timeRange.value) {
      await Promise.all([
        fetchTimeSeries(timeRange.value.startTime, timeRange.value.endTime),
        fetchQuenchEvents(timeRange.value.startTime, timeRange.value.endTime),
        fetchSummary(currentTime.value, true),
        fetchParticles(currentTime.value, 2500, true)
      ]);
    }
  }

  function dispose() {
    if (particlePool.value) {
      particlePool.value.dispose();
      particlePool.value = null;
    }
  }

  return {
    sensors,
    timeSeriesData,
    currentStats,
    particles,
    timeRange,
    currentTime,
    isPlaying,
    playbackSpeed,
    quenchEvents,
    isLoading,
    error,
    heatZoneTemperature,
    quenchDetected,
    activeSensors,
    boilingIntensity,
    particlePool,
    fetchSensors,
    fetchTimeRange,
    fetchTimeSeries,
    fetchSummary,
    fetchParticles,
    fetchQuenchEvents,
    setCurrentTime,
    togglePlayback,
    setPlaybackSpeed,
    stepForward,
    stepBackward,
    seekTo,
    initialize,
    getParticlePool,
    getPoolStats,
    advanceParticles,
    dispose
  };
});
