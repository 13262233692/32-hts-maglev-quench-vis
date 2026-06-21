<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { useDataStore } from '@/stores/dataStore';
import { useTimeSync } from '@/composables/useTimeSync';
import { COLORS, FONTS } from '@/types';
import { hexToRgba } from '@/utils/color';
import CryostatViewer from '@/components/CryostatViewer.vue';
import ResistivityChart from '@/components/ResistivityChart.vue';
import TimelineControl from '@/components/TimelineControl.vue';
import MetricCard from '@/components/MetricCard.vue';

const dataStore = useDataStore();
const isLoading = ref(true);
const loadError = ref<string | null>(null);

useTimeSync(50);

const currentTrend = computed(() => {
  if (!dataStore.currentStats) return 'stable';
  const temp = dataStore.currentStats.avgTemperature;
  if (temp > 85) return 'up';
  if (temp < 78) return 'down';
  return 'stable';
});

const temperatureStatus = computed(() => {
  if (!dataStore.currentStats) return 'normal';
  const temp = dataStore.currentStats.avgTemperature;
  if (temp > 90) return 'danger';
  if (temp > 82) return 'warning';
  return 'normal';
});

const resistivityStatus = computed(() => {
  return dataStore.quenchDetected ? 'danger' : 'normal';
});

async function initialize() {
  try {
    isLoading.value = true;
    await dataStore.initialize();
    isLoading.value = false;
  } catch (error) {
    console.error('Failed to initialize:', error);
    loadError.value = '无法连接到数据服务，将使用模拟数据';
    isLoading.value = false;
  }
}

function formatTime(seconds: number): string {
  const date = new Date(seconds * 1000);
  return date.toISOString().substr(11, 8);
}

const mainTitleStyle = computed(() => ({
  color: COLORS.primary,
  fontFamily: FONTS.display
}));

const dataChannelStyle = computed(() => ({
  color: COLORS.accent,
  fontFamily: FONTS.mono
}));

const dataStatusStyle = computed(() => ({
  color: dataStore.isLoading ? COLORS.warning : COLORS.success,
  fontFamily: FONTS.mono
}));

const loadingTextStyle = computed(() => ({
  color: COLORS.primary,
  fontFamily: FONTS.display
}));

const sensorPanelTitleStyle = computed(() => ({
  color: COLORS.primary,
  fontFamily: FONTS.display
}));

const quenchEventIdStyle = computed(() => ({
  color: COLORS.danger,
  fontFamily: FONTS.mono
}));

onMounted(() => {
  initialize();
});
</script>

<template>
  <div 
    class="main-container w-full h-full flex flex-col overflow-hidden relative"
    :style="{ background: COLORS.background }"
  >
    <div 
      class="absolute inset-0 pointer-events-none opacity-5"
      :style="{
        backgroundImage: `
          linear-gradient(${COLORS.primary} 1px, transparent 1px),
          linear-gradient(90deg, ${COLORS.primary} 1px, transparent 1px)
        `,
        backgroundSize: '50px 50px'
      }"
    />

    <div 
      class="absolute inset-0 pointer-events-none"
      :style="{
        background: `radial-gradient(ellipse at center top, ${hexToRgba(COLORS.primary, 0.15)} 0%, transparent 60%)`
      }"
    />

    <header class="header-bar relative z-10 px-6 py-3 flex items-center justify-between border-b-2"
      :style="{ borderColor: hexToRgba(COLORS.primary, 0.3) }"
    >
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-3">
          <div 
            class="w-10 h-10 rounded-lg flex items-center justify-center text-2xl"
            :style="{
              background: `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`,
              boxShadow: `0 0 20px ${hexToRgba(COLORS.primary, 0.5)}`
            }"
          >
            ❄️
          </div>
          <div>
            <h1 
              class="text-xl font-bold tracking-wider"
              :style="mainTitleStyle"
            >
              HTS 高温超导磁浮列车
            </h1>
            <p class="text-xs" :style="{ color: COLORS.textSecondary }">
              失超与热平衡态势可视化大屏 · QUENCH & THERMAL BALANCE VISUALIZATION
            </p>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-6">
        <div class="text-right">
          <div class="text-xs" :style="{ color: COLORS.textSecondary }">系统时间</div>
          <div 
            class="text-sm font-mono"
            :style="{ color: COLORS.secondary }"
          >
            {{ formatTime(Date.now() / 1000) }}
          </div>
        </div>
        
        <div 
          class="px-4 py-2 rounded-lg border"
          :style="{
            borderColor: hexToRgba(COLORS.accent, 0.5),
            background: hexToRgba(COLORS.accent, 0.1)
          }"
        >
          <div class="text-[10px] uppercase tracking-wider" :style="{ color: COLORS.textSecondary }">
            数据通道
          </div>
          <div 
            class="text-sm font-bold"
            :style="dataChannelStyle"
          >
            {{ dataStore.sensors.length }} 光纤探针
          </div>
        </div>

        <div 
          class="flex items-center gap-2 px-3 py-2 rounded-lg border"
          :style="{
            borderColor: dataStore.isLoading 
              ? hexToRgba(COLORS.warning, 0.5) 
              : hexToRgba(COLORS.success, 0.5),
            background: dataStore.isLoading
              ? hexToRgba(COLORS.warning, 0.1)
              : hexToRgba(COLORS.success, 0.1)
          }"
        >
          <div 
            class="w-2 h-2 rounded-full animate-pulse"
            :style="{
              backgroundColor: dataStore.isLoading ? COLORS.warning : COLORS.success
            }"
          />
          <span 
            class="text-xs"
            :style="dataStatusStyle"
          >
            {{ dataStore.isLoading ? '加载中...' : '数据在线' }}
          </span>
        </div>
      </div>
    </header>

    <div 
      v-if="isLoading"
      class="absolute inset-0 z-50 flex items-center justify-center"
      :style="{ background: hexToRgba(COLORS.background, 0.95) }"
    >
      <div class="text-center">
        <div 
          class="w-16 h-16 border-4 rounded-full animate-spin mx-auto mb-4"
          :style="{
            borderColor: `${COLORS.primary} transparent ${COLORS.secondary} transparent`
          }"
        />
        <p 
          class="text-lg"
          :style="loadingTextStyle"
        >
          正在初始化超导数据系统...
        </p>
        <p class="text-sm mt-2" :style="{ color: COLORS.textSecondary }">
          加载 {{ dataStore.sensors.length }} 通道历史数据
        </p>
      </div>
    </div>

    <div v-else class="flex-1 flex flex-col p-4 gap-4 relative z-10 overflow-hidden">
      <div class="metrics-row grid grid-cols-5 gap-4">
        <MetricCard
          title="平均电流密度"
          :value="dataStore.currentStats?.avgCurrentDensity || 0"
          unit="A/cm²"
          :color="COLORS.primary"
          :precision="1"
          status="normal"
        />
        <MetricCard
          title="最大电流密度"
          :value="dataStore.currentStats?.maxCurrentDensity || 0"
          unit="A/cm²"
          :color="COLORS.accent"
          :precision="1"
          status="normal"
        />
        <MetricCard
          title="平均温度"
          :value="dataStore.currentStats?.avgTemperature || 77"
          unit="K"
          :color="COLORS.secondary"
          :precision="2"
          :status="temperatureStatus"
          :trend="currentTrend"
        />
        <MetricCard
          title="平均磁场"
          :value="dataStore.currentStats?.avgMagneticField || 0"
          unit="T"
          :color="'#a29bfe'"
          :precision="2"
          status="normal"
        />
        <MetricCard
          title="平均电阻率"
          :value="dataStore.currentStats?.avgResistivity || 0"
          unit="Ω·m"
          :color="COLORS.danger"
          :precision="3"
          :status="resistivityStatus"
        />
      </div>

      <div class="content-row flex-1 flex gap-4 min-h-0">
        <div class="main-view flex-1 min-w-0">
          <CryostatViewer />
        </div>

        <div class="side-panel w-[480px] flex flex-col gap-4 min-w-0">
          <div class="flex-1 min-h-0">
            <ResistivityChart 
              :height="300"
              title="电阻率相变跃迁 · 通道 01-08"
            />
          </div>
          
          <div 
            class="sensor-panel rounded-lg border-2 p-4 flex-1 min-h-0 overflow-auto"
            :style="{
              borderColor: hexToRgba(COLORS.primary, 0.5),
              background: hexToRgba(COLORS.background, 0.7),
              backdropFilter: 'blur(8px)'
            }"
          >
            <div class="flex items-center justify-between mb-3">
              <h3 
                class="text-sm font-bold tracking-wider"
                :style="sensorPanelTitleStyle"
              >
                测点状态监控
              </h3>
              <span 
                class="text-xs px-2 py-1 rounded"
                :style="{ 
                  background: hexToRgba(COLORS.primary, 0.2),
                  color: COLORS.primary 
                }"
              >
                {{ dataStore.quenchDetected ? `${dataStore.activeSensors.length} 告警` : '全部正常' }}
              </span>
            </div>
            
            <div class="grid grid-cols-2 gap-2">
              <div
                v-for="(sensor, index) in dataStore.sensors.slice(0, 12)"
                :key="sensor.sensorId"
                class="sensor-item p-2 rounded border transition-all"
                :style="{
                  borderColor: dataStore.activeSensors.includes(sensor.sensorId)
                    ? hexToRgba(COLORS.danger, 0.6)
                    : hexToRgba(COLORS.primary, 0.2),
                  background: dataStore.activeSensors.includes(sensor.sensorId)
                    ? hexToRgba(COLORS.danger, 0.15)
                    : hexToRgba(COLORS.primary, 0.05)
                }"
              >
                <div class="flex items-center gap-2">
                  <div 
                    class="w-2 h-2 rounded-full"
                    :style="{
                      backgroundColor: dataStore.activeSensors.includes(sensor.sensorId)
                        ? COLORS.danger
                        : COLORS.success,
                      animation: dataStore.activeSensors.includes(sensor.sensorId)
                        ? 'pulse 1s infinite'
                        : 'none'
                    }"
                  />
                  <span 
                    class="text-xs font-mono"
                    :style="{ 
                      color: dataStore.activeSensors.includes(sensor.sensorId)
                        ? COLORS.danger
                        : COLORS.text
                    }"
                  >
                    {{ sensor.sensorId }}
                  </span>
                </div>
                <div class="text-[10px] mt-1" :style="{ color: COLORS.textSecondary }">
                  通道 {{ String(sensor.channel + 1).padStart(2, '0') }}
                </div>
              </div>
            </div>

            <div v-if="dataStore.quenchEvents.length > 0" class="mt-4 pt-4 border-t"
              :style="{ borderColor: hexToRgba(COLORS.danger, 0.3) }"
            >
              <h4 
                class="text-xs font-bold mb-2"
                :style="{ color: COLORS.danger }"
              >
                ⚠️ 失超事件记录
              </h4>
              <div class="space-y-1">
                <div
                  v-for="(event, index) in dataStore.quenchEvents.slice(0, 5)"
                  :key="index"
                  class="text-[10px] p-2 rounded"
                  :style="{ background: hexToRgba(COLORS.danger, 0.1) }"
                >
                  <div class="flex justify-between">
                    <span :style="quenchEventIdStyle">
                      {{ event.sensorId }}
                    </span>
                    <span :style="{ color: COLORS.textSecondary }">
                      t = {{ event.startTime.toFixed(1) }}s
                    </span>
                  </div>
                  <div class="mt-1" :style="{ color: COLORS.textSecondary }">
                    峰值: {{ event.peakResistivity.toExponential(2) }} Ω·m · {{ event.peakTemperature.toFixed(1) }} K
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="timeline-row">
        <TimelineControl />
      </div>
    </div>

    <div 
      v-if="loadError"
      class="absolute bottom-24 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg border text-sm"
      :style="{
        background: hexToRgba(COLORS.warning, 0.2),
        borderColor: COLORS.warning,
        color: COLORS.warning
      }"
    >
      {{ loadError }}
    </div>
  </div>
</template>

<style scoped>
.main-container {
  min-height: 100vh;
}

.sensor-item:hover {
  transform: translateY(-1px);
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}
</style>
