<script setup lang="ts">
import { computed } from 'vue';
import { COLORS, FONTS } from '@/types';
import { hexToRgba } from '@/utils/color';

interface Props {
  title: string;
  value: number;
  unit: string;
  color?: string;
  precision?: number;
  status?: 'normal' | 'warning' | 'danger';
  trend?: 'up' | 'down' | 'stable';
}

const props = withDefaults(defineProps<Props>(), {
  color: COLORS.primary,
  precision: 2,
  status: 'normal'
});

const statusColor = computed(() => {
  switch (props.status) {
    case 'danger': return COLORS.danger;
    case 'warning': return COLORS.warning;
    default: return COLORS.success;
  }
});

const formattedValue = computed(() => {
  if (props.value === undefined || props.value === null) return '--';
  if (Math.abs(props.value) < 0.0001) {
    return props.value.toExponential(props.precision);
  }
  return props.value.toFixed(props.precision);
});

const valueStyle = computed(() => ({
  color: props.color,
  fontFamily: FONTS.display
}));
</script>

<template>
  <div 
    class="metric-card relative overflow-hidden rounded-lg border backdrop-blur-md transition-all duration-300"
    :style="{
      background: hexToRgba(COLORS.background, 0.7),
      borderColor: hexToRgba(color, 0.4),
      boxShadow: `0 0 20px ${hexToRgba(color, 0.2)}`
    }"
  >
    <div class="p-4">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-medium tracking-wider" :style="{ color: COLORS.textSecondary }">
          {{ title }}
        </span>
        <div 
          class="w-2 h-2 rounded-full animate-pulse"
          :style="{ backgroundColor: statusColor }"
        />
      </div>
      <div class="flex items-baseline gap-2">
        <span 
          class="text-2xl font-bold tracking-tight"
          :style="valueStyle"
        >
          {{ formattedValue }}
        </span>
        <span class="text-xs" :style="{ color: COLORS.textSecondary }">
          {{ unit }}
        </span>
      </div>
      <div v-if="trend" class="mt-2 flex items-center gap-1 text-xs">
        <span v-if="trend === 'up'" class="text-red-400">↑</span>
        <span v-else-if="trend === 'down'" class="text-green-400">↓</span>
        <span v-else class="text-gray-400">→</span>
        <span :style="{ color: COLORS.textSecondary }">
          {{ trend === 'up' ? '上升' : trend === 'down' ? '下降' : '稳定' }}
        </span>
      </div>
    </div>
    <div 
      class="absolute bottom-0 left-0 h-1 transition-all duration-500"
      :style="{
        width: status === 'normal' ? '100%' : status === 'warning' ? '60%' : '30%',
        backgroundColor: status === 'normal' ? COLORS.success : status === 'warning' ? COLORS.warning : COLORS.danger,
        boxShadow: `0 0 10px ${statusColor}`
      }"
    />
  </div>
</template>

<style scoped>
.metric-card {
  min-width: 180px;
}
</style>
