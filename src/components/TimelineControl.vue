<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { Play, Pause, SkipBack, SkipForward, RotateCcw, Gauge } from 'lucide-vue-next';
import { useDataStore } from '@/stores/dataStore';
import { COLORS, FONTS } from '@/types';
import { hexToRgba } from '@/utils/color';

const dataStore = useDataStore();
const showSpeedMenu = ref(false);

const playbackSpeeds = [0.5, 1, 2, 5, 10];

const progressPercent = computed(() => {
  const range = dataStore.timeRange.endTime - dataStore.timeRange.startTime;
  if (range <= 0) return 0;
  return ((dataStore.currentTime - dataStore.timeRange.startTime) / range) * 100;
});

const quenchMarkers = computed(() => {
  const range = dataStore.timeRange.endTime - dataStore.timeRange.startTime;
  if (range <= 0) return [];
  
  return dataStore.quenchEvents.map(event => ({
    left: ((event.startTime - dataStore.timeRange.startTime) / range) * 100,
    sensorId: event.sensorId
  }));
});

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms}`;
}

function handleProgressClick(event: MouseEvent) {
  const target = event.currentTarget as HTMLElement;
  const rect = target.getBoundingClientRect();
  const percent = (event.clientX - rect.left) / rect.width;
  const newTime = dataStore.timeRange.startTime + 
    percent * (dataStore.timeRange.endTime - dataStore.timeRange.startTime);
  dataStore.seekTo(newTime);
}

function togglePlay() {
  dataStore.togglePlayback();
}

function stepBackward() {
  dataStore.stepBackward(5);
}

function stepForward() {
  dataStore.stepForward(5);
}

function reset() {
  dataStore.setCurrentTime(dataStore.timeRange.startTime);
  if (dataStore.isPlaying) {
    dataStore.togglePlayback();
  }
}

function setSpeed(speed: number) {
  dataStore.setPlaybackSpeed(speed);
  showSpeedMenu.value = false;
}

const progressStyle = computed(() => ({
  background: `linear-gradient(to right, 
    ${COLORS.primary} 0%, 
    ${COLORS.secondary} ${progressPercent.value}%, 
    ${hexToRgba(COLORS.primary, 0.2)} ${progressPercent.value}%
  )`
}));

const speedButtonStyle = computed(() => (speed: number) => ({
  color: dataStore.playbackSpeed === speed ? COLORS.accent : COLORS.textSecondary,
  background: dataStore.playbackSpeed === speed ? hexToRgba(COLORS.accent, 0.2) : 'transparent',
  fontFamily: FONTS.mono
}));

const currentTimeStyle = computed(() => ({
  color: dataStore.quenchDetected ? COLORS.danger : COLORS.primary,
  fontFamily: FONTS.display,
  textShadow: dataStore.quenchDetected 
    ? `0 0 10px ${COLORS.danger}` 
    : `0 0 10px ${hexToRgba(COLORS.primary, 0.5)}`
}));

const systemStatusStyle = computed(() => ({
  color: dataStore.quenchDetected ? COLORS.danger : COLORS.success,
  fontFamily: FONTS.display
}));
</script>

<template>
  <div 
    class="timeline-control px-6 py-4 rounded-lg border-2"
    :style="{
      background: hexToRgba(COLORS.background, 0.85),
      borderColor: hexToRgba(COLORS.primary, 0.5),
      backdropFilter: 'blur(10px)'
    }"
  >
    <div class="flex items-center gap-6">
      <div class="flex items-center gap-2">
        <button
          class="control-btn p-2 rounded-md transition-all hover:scale-105"
          :style="{
            background: hexToRgba(COLORS.primary, 0.15),
            color: COLORS.secondary
          }"
          @click="reset"
          title="重置"
        >
          <RotateCcw :size="18" />
        </button>
        
        <button
          class="control-btn p-2 rounded-md transition-all hover:scale-105"
          :style="{
            background: hexToRgba(COLORS.primary, 0.15),
            color: COLORS.primary
          }"
          @click="stepBackward"
          title="后退5秒"
        >
          <SkipBack :size="18" />
        </button>
        
        <button
          class="play-btn p-3 rounded-full transition-all hover:scale-110 active:scale-95"
          :style="{
            background: dataStore.isPlaying 
              ? `linear-gradient(135deg, ${COLORS.danger}, ${COLORS.warning})`
              : `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.secondary})`,
            color: COLORS.background,
            boxShadow: dataStore.isPlaying
              ? `0 0 20px ${hexToRgba(COLORS.danger, 0.5)}`
              : `0 0 20px ${hexToRgba(COLORS.primary, 0.5)}`
          }"
          @click="togglePlay"
          :title="dataStore.isPlaying ? '暂停' : '播放'"
        >
          <Pause v-if="dataStore.isPlaying" :size="24" />
          <Play v-else :size="24" />
        </button>
        
        <button
          class="control-btn p-2 rounded-md transition-all hover:scale-105"
          :style="{
            background: hexToRgba(COLORS.primary, 0.15),
            color: COLORS.primary
          }"
          @click="stepForward"
          title="前进5秒"
        >
          <SkipForward :size="18" />
        </button>

        <div class="relative">
          <button
            class="control-btn p-2 rounded-md transition-all hover:scale-105 flex items-center gap-1"
            :style="{
              background: hexToRgba(COLORS.accent, 0.2),
              color: COLORS.accent
            }"
            @click="showSpeedMenu = !showSpeedMenu"
            title="播放速度"
          >
            <Gauge :size="16" />
            <span class="text-xs font-bold" style="font-family: 'JetBrains Mono', monospace;">
              {{ dataStore.playbackSpeed }}x
            </span>
          </button>
          
          <div
            v-if="showSpeedMenu"
            class="absolute bottom-full left-0 mb-2 py-2 rounded-lg border shadow-xl z-50"
            :style="{
              background: COLORS.background,
              borderColor: hexToRgba(COLORS.accent, 0.5)
            }"
          >
            <button
              v-for="speed in playbackSpeeds"
              :key="speed"
              class="w-full px-4 py-2 text-left text-sm transition-colors"
              :style="speedButtonStyle(speed)"
              @click="setSpeed(speed)"
            >
              {{ speed }}x 速度
            </button>
          </div>
        </div>
      </div>

      <div class="flex-1">
        <div 
          class="progress-track relative h-3 rounded-full cursor-pointer overflow-hidden"
          :style="{
            background: hexToRgba(COLORS.primary, 0.15),
            boxShadow: `inset 0 2px 4px ${hexToRgba(COLORS.background, 0.5)}`
          }"
          @click="handleProgressClick"
        >
          <div 
            class="progress-bar h-full rounded-full transition-all duration-75"
            :style="progressStyle"
          />
          
          <div
            v-for="(marker, index) in quenchMarkers"
            :key="index"
            class="absolute top-0 bottom-0 w-0.5 animate-pulse"
            :style="{
              left: marker.left + '%',
              background: COLORS.danger,
              boxShadow: `0 0 8px ${COLORS.danger}`
            }"
            :title="`失超: ${marker.sensorId}`"
          />
          
          <div 
            class="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 transition-all"
            :style="{
              left: `calc(${progressPercent}% - 8px)`,
              background: COLORS.secondary,
              borderColor: COLORS.background,
              boxShadow: `0 0 12px ${COLORS.secondary}`
            }"
          />
        </div>
        
        <div class="flex justify-between mt-2 text-xs">
          <span 
            class="font-mono"
            :style="{ color: COLORS.textSecondary }"
          >
            {{ formatTime(dataStore.timeRange.startTime) }}
          </span>
          <span 
            class="font-mono text-lg font-bold"
            :style="currentTimeStyle"
          >
            {{ formatTime(dataStore.currentTime) }}
          </span>
          <span 
            class="font-mono"
            :style="{ color: COLORS.textSecondary }"
          >
            {{ formatTime(dataStore.timeRange.endTime) }}
          </span>
        </div>
      </div>

      <div 
        class="px-4 py-2 rounded-lg border text-center min-w-[120px]"
        :style="{
          borderColor: dataStore.quenchDetected 
            ? hexToRgba(COLORS.danger, 0.5) 
            : hexToRgba(COLORS.success, 0.5),
          background: dataStore.quenchDetected
            ? hexToRgba(COLORS.danger, 0.15)
            : hexToRgba(COLORS.success, 0.1)
        }"
      >
        <div 
          class="text-[10px] uppercase tracking-wider"
          :style="{ color: COLORS.textSecondary }"
        >
          系统状态
        </div>
        <div 
          class="text-sm font-bold"
          :style="systemStatusStyle"
        >
          {{ dataStore.quenchDetected ? '⚠ 失超中' : '✓ 超导态' }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.control-btn:hover {
  filter: brightness(1.2);
}

.progress-track:hover .progress-bar {
  filter: brightness(1.2);
}
</style>
