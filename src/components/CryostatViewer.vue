<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue';
import { useDataStore } from '@/stores/dataStore';
import { useDeckGl } from '@/composables/useDeckGl';
import { COLORS, FONTS } from '@/types';
import { hexToRgba } from '@/utils/color';

const containerRef = ref<HTMLElement | null>(null);
const dimensions = ref({ width: 800, height: 600 });
const dataStore = useDataStore();

const deckGl = useDeckGl({
  container: containerRef.value,
  width: dimensions.value.width,
  height: dimensions.value.height
});

const quenchAlertStyle = computed(() => ({
  opacity: dataStore.quenchDetected ? 1 : 0,
  transform: dataStore.quenchDetected ? 'translateY(0)' : 'translateY(-20px)'
}));

const cryostatTitleStyle = computed(() => ({
  color: COLORS.primary,
  fontFamily: FONTS.display
}));

const quenchAlertTextStyle = computed(() => ({
  color: COLORS.danger,
  fontFamily: FONTS.display
}));

function handleResize() {
  if (containerRef.value) {
    const rect = containerRef.value.getBoundingClientRect();
    dimensions.value = {
      width: rect.width,
      height: rect.height
    };
    deckGl.resize(rect.width, rect.height);
  }
}

watch(
  () => [dataStore.particles, dataStore.sensors, dataStore.heatZoneTemperature, dataStore.quenchDetected],
  () => {
    deckGl.update(
      dataStore.particles,
      dataStore.sensors,
      dataStore.heatZoneTemperature,
      dataStore.quenchDetected
    );
  },
  { deep: true }
);

onMounted(() => {
  handleResize();
  window.addEventListener('resize', handleResize);
  
  setTimeout(() => {
    deckGl.initialize();
    deckGl.update(
      dataStore.particles,
      dataStore.sensors,
      dataStore.heatZoneTemperature,
      dataStore.quenchDetected
    );
  }, 100);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
});
</script>

<template>
  <div 
    class="cryostat-viewer relative w-full h-full rounded-lg overflow-hidden border-2"
    :style="{ borderColor: hexToRgba(COLORS.primary, 0.5) }"
  >
    <div 
      class="absolute top-4 left-4 z-10 px-4 py-2 rounded-lg backdrop-blur-md border"
      :style="{
        background: hexToRgba(COLORS.background, 0.8),
        borderColor: hexToRgba(COLORS.primary, 0.3)
      }"
    >
      <div class="text-xs" :style="{ color: COLORS.textSecondary }">超导杜瓦瓶 · 三维剖面</div>
      <div class="text-lg font-bold" :style="cryostatTitleStyle">
        CRYOSTAT-01
      </div>
    </div>

    <div 
      class="absolute top-4 right-4 z-10 flex flex-col gap-2"
    >
      <div 
        class="px-3 py-1 rounded backdrop-blur-md border text-xs"
        :style="{
          background: hexToRgba(COLORS.background, 0.8),
          borderColor: hexToRgba(COLORS.secondary, 0.3),
          color: COLORS.secondary
        }"
      >
        粒子数: {{ dataStore.particles.length }}
      </div>
      <div 
        class="px-3 py-1 rounded backdrop-blur-md border text-xs"
        :style="{
          background: hexToRgba(COLORS.background, 0.8),
          borderColor: hexToRgba(COLORS.warning, 0.3),
          color: COLORS.warning
        }"
      >
        热区温度: {{ dataStore.heatZoneTemperature.toFixed(2) }} K
      </div>
    </div>

    <div 
      class="absolute top-20 left-1/2 -translate-x-1/2 z-20 px-6 py-3 rounded-lg backdrop-blur-md border-2 transition-all duration-300"
      :style="{
        ...quenchAlertStyle,
        background: hexToRgba(COLORS.danger, 0.2),
        borderColor: COLORS.danger,
        boxShadow: `0 0 30px ${hexToRgba(COLORS.danger, 0.5)}`
      }"
    >
      <div class="flex items-center gap-3">
        <div class="w-3 h-3 rounded-full animate-ping" :style="{ backgroundColor: COLORS.danger }" />
        <span class="text-lg font-bold" :style="quenchAlertTextStyle">
          ⚠️ 失超检测中 · QUENCH DETECTED
        </span>
        <div class="w-3 h-3 rounded-full animate-ping" :style="{ backgroundColor: COLORS.danger }" />
      </div>
    </div>

    <div 
      class="absolute bottom-4 left-4 z-10 text-xs space-y-1"
      :style="{ color: COLORS.textSecondary }"
    >
      <div>• 拖拽旋转视角</div>
      <div>• 滚轮缩放</div>
    </div>

    <div 
      class="absolute bottom-4 right-4 z-10 px-3 py-2 rounded-lg backdrop-blur-md border text-xs"
      :style="{
        background: hexToRgba(COLORS.background, 0.8),
        borderColor: hexToRgba(COLORS.accent, 0.3)
      }"
    >
      <div class="mb-1" :style="{ color: COLORS.textSecondary }">温度色标</div>
      <div class="flex items-center gap-2">
        <div 
          class="w-20 h-2 rounded"
          :style="{
            background: 'linear-gradient(to right, #00d4ff, #00ffd5, #ffa502, #ff4757)'
          }"
        />
        <div class="flex justify-between w-20 text-[10px]">
          <span :style="{ color: COLORS.primary }">77K</span>
          <span :style="{ color: COLORS.danger }">120K</span>
        </div>
      </div>
    </div>

    <div 
      ref="containerRef"
      class="w-full h-full"
    >
      <canvas 
        id="cryostat-canvas" 
        class="w-full h-full"
      />
    </div>
  </div>
</template>

<style scoped>
.cryostat-viewer {
  background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 50%, #0a1628 100%);
}

#cryostat-canvas {
  display: block;
}
</style>
