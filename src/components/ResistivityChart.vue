<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue';
import * as echarts from 'echarts';
import { useDataStore } from '@/stores/dataStore';
import { COLORS, SENSOR_COLORS, FONTS } from '@/types';
import { hexToRgba } from '@/utils/color';
import type { PredictionPoint, HeaterEvent } from '@/types';

interface Props {
  height?: number;
  title?: string;
}

const props = withDefaults(defineProps<Props>(), {
  height: 300,
  title: '电阻率相变跃迁曲线'
});

const chartRef = ref<HTMLDivElement | null>(null);
let chartInstance: echarts.ECharts | null = null;
const dataStore = useDataStore();

const RESISTIVITY_THRESHOLD = 1e-10;
const BURN_THRESHOLD = 1e-5;

const displaySensors = computed(() => {
  return dataStore.sensors.slice(0, 4);
});

const primarySensor = computed(() => {
  if (dataStore.predictionSensorId) {
    return dataStore.predictionSensorId;
  }
  return displaySensors.value[0]?.sensorId || null;
});

function buildPredictionSeries(sensorId: string, color: string, pred: any) {
  const series: any[] = [];
  const ts = pred.timeSeries as PredictionPoint[] | undefined;
  if (!ts || ts.length === 0) return series;

  const midData = ts.map(p => [p.timestamp, p.resistivity]);

  const upperData = ts.map(p => [p.timestamp, p.rhoUpper]);
  const lowerData = [...ts].reverse().map(p => [p.timestamp, p.rhoLower]);
  const confidenceData = [...upperData, ...lowerData];

  series.push({
    name: `${sensorId} 置信区间`,
    type: 'line',
    data: confidenceData,
    symbol: 'none',
    lineStyle: { opacity: 0 },
    areaStyle: {
      color: hexToRgba(color, 0.15),
      origin: 'auto'
    },
    stack: 'confidence',
    silent: true,
    animation: false,
    z: 1
  });

  series.push({
    name: `${sensorId} 预计失超`,
    type: 'line',
    data: midData,
    smooth: true,
    symbol: 'none',
    lineStyle: {
      width: 2.5,
      type: 'dashed',
      color: color,
      shadowBlur: 10,
      shadowColor: color
    },
    animation: false,
    z: 3
  });

  return series;
}

function buildHeaterMarkPoints(heaterEvents: HeaterEvent[], sensorColor: string) {
  return heaterEvents.map(evt => ({
    name: `加热器触发·${evt.sensorId}`,
    xAxis: evt.triggerTime,
    yAxis: evt.triggerResistivity,
    symbol: 'triangle',
    symbolSize: 18,
    itemStyle: {
      color: '#ff0033',
      borderColor: '#ff6666',
      borderWidth: 2,
      shadowBlur: 15,
      shadowColor: '#ff0033'
    },
    label: {
      show: true,
      formatter: '⏚',
      color: '#ffffff',
      fontSize: 12,
      fontWeight: 'bold'
    },
    emphasis: {
      itemStyle: {
        shadowBlur: 30,
        shadowColor: '#ff0000'
      }
    },
    tooltip: {
      formatter: () => `
        <div style="font-weight:bold;color:#ff4757;margin-bottom:4px;">
          ⏚ 二次保护加热器触发
        </div>
        <div>传感器: ${evt.sensorId}</div>
        <div>触发时间: ${evt.triggerTime.toFixed(3)}s</div>
        <div>触发电阻率: ${evt.triggerResistivity.toExponential(2)} Ω·m</div>
        <div>预警延迟: ${evt.delayMs.toFixed(0)}ms</div>
        <div>传播速度: ${evt.propagationVelocity.toFixed(2)} m/s</div>
        <div style="color:#ff9500;font-weight:bold;">严重等级: ${evt.severity}</div>
      `
    }
  }));
}

function prepareChartData() {
  const series: echarts.SeriesOption[] = [];
  const legendData: string[] = [];

  displaySensors.value.forEach((sensor, index) => {
    const sensorData = dataStore.timeSeriesData
      .filter(d => d.sensorId === sensor.sensorId)
      .sort((a, b) => a.timestamp - b.timestamp);

    if (sensorData.length > 0) {
      const color = SENSOR_COLORS[index % SENSOR_COLORS.length];

      series.push({
        name: sensor.sensorId,
        type: 'line',
        data: sensorData.map(d => [d.timestamp, d.resistivity]),
        smooth: true,
        symbol: 'none',
        lineStyle: {
          width: 2,
          color,
          opacity: 0.9
        },
        emphasis: {
          focus: 'series',
          lineStyle: { width: 4 }
        },
        animation: false,
        z: 2
      });

      legendData.push(sensor.sensorId);

      const pred = dataStore.quenchPredictions[sensor.sensorId];
      if (pred && pred.status === 'quenching' && pred.timeSeries) {
        const predSeries = buildPredictionSeries(sensor.sensorId, color, pred);
        series.push(...predSeries);
      }
    }
  });

  series.push({
    name: '零电阻阈值',
    type: 'line',
    data: [
      [dataStore.timeRange.startTime, RESISTIVITY_THRESHOLD],
      [dataStore.timeRange.endTime, RESISTIVITY_THRESHOLD]
    ],
    symbol: 'none',
    lineStyle: {
      width: 2,
      type: 'dashed',
      color: COLORS.danger
    },
    z: 1
  });

  series.push({
    name: '烧毁阈值',
    type: 'line',
    data: [
      [dataStore.timeRange.startTime, BURN_THRESHOLD],
      [dataStore.timeRange.endTime, BURN_THRESHOLD]
    ],
    symbol: 'none',
    lineStyle: {
      width: 1.5,
      type: 'dotted',
      color: '#ff0033'
    },
    z: 1
  });

  return { series, legendData };
}

function applyHeaterMarkPoints(series: any[]) {
  if (dataStore.heaterEvents.length === 0) return;

  const firstSensorSeries = series.find(
    (s: any) => s.name && !s.name.includes('置信') && !s.name.includes('预计') &&
      !s.name.includes('阈值')
  );
  if (!firstSensorSeries) return;

  const sensorEvents = dataStore.heaterEvents.filter(
    evt => firstSensorSeries.name === evt.sensorId
  );
  if (sensorEvents.length === 0) return;

  firstSensorSeries.markPoint = {
    data: buildHeaterMarkPoints(sensorEvents, '#ff4757'),
    symbol: 'triangle',
    symbolSize: 20,
    animation: true,
    animationDuration: 800,
    animationEasing: 'elasticOut'
  };
}

function createChart() {
  if (!chartRef.value) return;

  chartInstance = echarts.init(chartRef.value);

  const { series, legendData } = prepareChartData();
  applyHeaterMarkPoints(series as any[]);

  const option: echarts.EChartsOption = {
    backgroundColor: 'transparent',
    animation: false,
    title: {
      text: props.title,
      left: 'center',
      top: 10,
      textStyle: {
        color: COLORS.primary,
        fontSize: 14,
        fontFamily: FONTS.display
      }
    },
    legend: {
      data: legendData,
      top: 35,
      left: 'center',
      textStyle: {
        color: COLORS.textSecondary,
        fontSize: 10
      },
      itemWidth: 20,
      itemHeight: 2
    },
    grid: {
      left: 60,
      right: 20,
      top: 70,
      bottom: 40
    },
    xAxis: {
      type: 'value',
      name: '时间 (s)',
      nameLocation: 'middle',
      nameGap: 25,
      nameTextStyle: {
        color: COLORS.textSecondary,
        fontSize: 11
      },
      min: dataStore.timeRange.startTime,
      max: dataStore.timeRange.endTime + 3,
      axisLine: {
        lineStyle: { color: COLORS.textSecondary }
      },
      axisLabel: {
        color: COLORS.textSecondary,
        fontSize: 10
      },
      splitLine: {
        lineStyle: { color: hexToRgba(COLORS.primary, 0.1) }
      }
    },
    yAxis: {
      type: 'log',
      name: '电阻率 (Ω·m)',
      nameLocation: 'middle',
      nameGap: 45,
      nameTextStyle: {
        color: COLORS.textSecondary,
        fontSize: 11
      },
      min: 1e-12,
      max: 1e-4,
      axisLine: {
        lineStyle: { color: COLORS.textSecondary }
      },
      axisLabel: {
        color: COLORS.textSecondary,
        fontSize: 10,
        formatter: (value: number) => {
          if (value >= 1e-10 && value < 1e-9) return '1e-10';
          if (value >= 1e-9 && value < 1e-8) return '1e-9';
          if (value >= 1e-8 && value < 1e-7) return '1e-8';
          if (value >= 1e-7 && value < 1e-6) return '1e-7';
          if (value >= 1e-6 && value < 1e-5) return '1e-6';
          if (value >= 1e-5 && value < 1e-4) return '1e-5';
          return value.toExponential(0);
        }
      },
      splitLine: {
        lineStyle: { color: hexToRgba(COLORS.primary, 0.1) }
      }
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: hexToRgba(COLORS.background, 0.95),
      borderColor: COLORS.primary,
      borderWidth: 1,
      textStyle: {
        color: COLORS.text,
        fontSize: 11
      },
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return '';
        const time = params[0].value[0].toFixed(2);
        let html = `<div style="font-weight:bold;color:${COLORS.primary};margin-bottom:5px;">时间: ${time}s</div>`;
        params.forEach((item: any) => {
          if (item.seriesName === '零电阻阈值' || item.seriesName === '烧毁阈值') return;
          const val = item.value[1];
          const color = item.color;
          const isAbove = val > RESISTIVITY_THRESHOLD;
          const isPred = item.seriesName.includes('预计');
          const isConf = item.seriesName.includes('置信');
          if (isConf) return;
          html += `<div style="display:flex;align-items:center;gap:5px;margin:2px 0;">
            <span style="width:10px;height:2px;background:${color};${isPred ? 'border-bottom:1px dashed' : ''}"></span>
            <span>${item.seriesName}:</span>
            <span style="font-family:monospace;${isAbove ? `color:${COLORS.danger};font-weight:bold;` : ''}">
              ${val.toExponential(2)} Ω·m
            </span>
            ${isPred ? '<span style="color:' + COLORS.warning + ';">预测</span>' : ''}
            ${isAbove && !isPred ? '<span style="color:' + COLORS.danger + ';">⚠</span>' : ''}
          </div>`;
        });
        return html;
      }
    },
    series,
    graphic: [
      {
        type: 'line',
        id: 'time-cursor',
        shape: { x1: 0, y1: 0, x2: 0, y2: 0 },
        style: {
          stroke: COLORS.secondary,
          lineWidth: 2,
          opacity: 0.8
        },
        silent: true
      },
      {
        type: 'text',
        id: 'time-label',
        style: {
          text: '',
          fill: COLORS.secondary,
          fontSize: 11,
          fontFamily: FONTS.mono
        },
        silent: true
      }
    ]
  };

  chartInstance.setOption(option);
  updateTimeCursor();
}

function updateTimeCursor() {
  if (!chartInstance || dataStore.currentTime === undefined || dataStore.currentTime === null) return;

  const option = chartInstance.getOption();
  const grid = option.grid[0];

  const chartWidth = chartRef.value?.clientWidth || 0;
  const chartHeight = chartRef.value?.clientHeight || 0;

  const xStart = grid.left || 60;
  const xEnd = chartWidth - (grid.right || 20);
  const yStart = grid.top || 70;
  const yEnd = chartHeight - (grid.bottom || 40);

  const timeRange = dataStore.timeRange.endTime - dataStore.timeRange.startTime;
  if (timeRange <= 0) return;

  const xPos = xStart + ((dataStore.currentTime - dataStore.timeRange.startTime) / timeRange) * (xEnd - xStart);

  chartInstance.setOption({
    graphic: [
      {
        id: 'time-cursor',
        $action: 'replace',
        type: 'line',
        shape: {
          x1: xPos, y1: yStart,
          x2: xPos, y2: yEnd
        },
        style: {
          stroke: COLORS.secondary,
          lineWidth: 2,
          opacity: 0.9,
          shadowBlur: 10,
          shadowColor: COLORS.secondary
        },
        silent: true
      },
      {
        id: 'time-label',
        $action: 'replace',
        type: 'text',
        left: Math.min(Math.max(xPos - 30, xStart), xEnd - 60),
        top: yStart - 20,
        style: {
          text: `t = ${dataStore.currentTime.toFixed(1)}s`,
          fill: COLORS.secondary,
          fontSize: 11,
          fontFamily: '"JetBrains Mono", monospace',
          backgroundColor: hexToRgba(COLORS.background, 0.8),
          padding: [2, 6]
        },
        silent: true
      }
    ]
  });
}

function highlightQuenchPoints() {
  if (!chartInstance) return;

  const markPoints = dataStore.quenchEvents
    .filter(e => displaySensors.value.some(s => s.sensorId === e.sensorId))
    .map(event => ({
      name: event.sensorId,
      xAxis: event.startTime,
      yAxis: event.peakResistivity,
      itemStyle: { color: COLORS.danger },
      label: {
        show: true,
        formatter: '⚠',
        color: COLORS.danger,
        fontSize: 14
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 20,
          shadowColor: COLORS.danger
        }
      }
    }));

  if (markPoints.length > 0) {
    const option = chartInstance.getOption();
    const series = option.series as any[];
    const firstSensorIdx = series.findIndex(
      (s: any) => s.name && displaySensors.value.some(sn => sn.sensorId === s.name)
    );
    if (firstSensorIdx >= 0) {
      series[firstSensorIdx].markPoint = {
        data: markPoints,
        symbol: 'pin',
        symbolSize: 30,
        animation: true,
        animationDuration: 1000
      };
      chartInstance.setOption({ series });
    }
  }
}

function handleResize() {
  chartInstance?.resize();
}

watch(
  () => dataStore.currentTime,
  () => { updateTimeCursor(); }
);

watch(
  () => dataStore.timeSeriesData,
  () => {
    if (chartInstance) {
      const { series } = prepareChartData();
      applyHeaterMarkPoints(series as any[]);
      chartInstance.setOption({ series });
      highlightQuenchPoints();
    }
  },
  { deep: true }
);

watch(
  () => dataStore.quenchPredictions,
  () => {
    if (chartInstance) {
      const { series } = prepareChartData();
      applyHeaterMarkPoints(series as any[]);
      chartInstance.setOption({ series });
    }
  },
  { deep: true }
);

watch(
  () => dataStore.heaterEvents,
  () => {
    if (chartInstance) {
      const { series } = prepareChartData();
      applyHeaterMarkPoints(series as any[]);
      chartInstance.setOption({ series });
    }
  },
  { deep: true }
);

watch(
  () => dataStore.quenchEvents,
  () => { highlightQuenchPoints(); },
  { deep: true }
);

onMounted(() => {
  createChart();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  chartInstance?.dispose();
});
</script>

<template>
  <div
    class="resistivity-chart rounded-lg border-2 overflow-hidden"
    :style="{
      borderColor: hexToRgba(COLORS.primary, 0.5),
      background: hexToRgba(COLORS.background, 0.7)
    }"
  >
    <div
      ref="chartRef"
      class="w-full"
      :style="{ height: height + 'px' }"
    />

    <div class="legend-strip" v-if="dataStore.heaterEvents.length > 0">
      <span class="heater-dot"></span>
      <span class="heater-text">
        ⏚ 二次保护加热器链路就绪 · {{ dataStore.heaterEvents.length }} 个触发点
      </span>
    </div>
  </div>
</template>

<style scoped>
.resistivity-chart {
  backdrop-filter: blur(8px);
  position: relative;
}

.legend-strip {
  position: absolute;
  top: 38px;
  right: 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(255, 0, 51, 0.15);
  border: 1px solid rgba(255, 0, 51, 0.4);
  border-radius: 4px;
  backdrop-filter: blur(4px);
}

.heater-dot {
  width: 8px;
  height: 8px;
  background: #ff0033;
  border-radius: 50%;
  box-shadow: 0 0 8px #ff0033;
  animation: pulse 1.5s ease-in-out infinite;
}

.heater-text {
  font-size: 10px;
  color: #ff6666;
  font-family: var(--font-mono);
  letter-spacing: 0.5px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
