<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue';
import * as echarts from 'echarts';
import { useDataStore } from '@/stores/dataStore';
import { COLORS, SENSOR_COLORS, FONTS } from '@/types';
import { hexToRgba } from '@/utils/color';

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

const displaySensors = computed(() => {
  return dataStore.sensors.slice(0, 8);
});

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
          opacity: 0.8
        },
        emphasis: {
          focus: 'series',
          lineStyle: {
            width: 4
          }
        },
        animation: false
      });
      
      legendData.push(sensor.sensorId);
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
    markLine: {
      silent: true,
      symbol: 'none',
      lineStyle: {
        color: COLORS.danger,
        type: 'dashed',
        width: 2
      },
      label: {
        formatter: 'ρc = 1e-10 Ω·m',
        position: 'end',
        color: COLORS.danger,
        fontSize: 10
      },
      data: [{
        yAxis: RESISTIVITY_THRESHOLD
      }]
    }
  });

  return { series, legendData };
}

function createChart() {
  if (!chartRef.value) return;

  chartInstance = echarts.init(chartRef.value);
  
  const { series, legendData } = prepareChartData();

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
      max: dataStore.timeRange.endTime,
      axisLine: {
        lineStyle: {
          color: COLORS.textSecondary
        }
      },
      axisLabel: {
        color: COLORS.textSecondary,
        fontSize: 10
      },
      splitLine: {
        lineStyle: {
          color: hexToRgba(COLORS.primary, 0.1)
        }
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
      max: 1e-6,
      axisLine: {
        lineStyle: {
          color: COLORS.textSecondary
        }
      },
      axisLabel: {
        color: COLORS.textSecondary,
        fontSize: 10,
        formatter: (value: number) => {
          if (value >= 1e-10 && value < 1e-9) return '1e-10';
          if (value >= 1e-9 && value < 1e-8) return '1e-9';
          if (value >= 1e-8 && value < 1e-7) return '1e-8';
          if (value >= 1e-7 && value < 1e-6) return '1e-7';
          return value.toExponential(0);
        }
      },
      splitLine: {
        lineStyle: {
          color: hexToRgba(COLORS.primary, 0.1)
        }
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
          if (item.seriesName !== '零电阻阈值') {
            const val = item.value[1];
            const color = item.color;
            const isAbove = val > RESISTIVITY_THRESHOLD;
            html += `<div style="display:flex;align-items:center;gap:5px;margin:2px 0;">
              <span style="width:10px;height:2px;background:${color};"></span>
              <span>${item.seriesName}:</span>
              <span style="font-family:monospace;${isAbove ? `color:${COLORS.danger};font-weight:bold;` : ''}">
                ${val.toExponential(2)} Ω·m
              </span>
              ${isAbove ? '<span style="color:' + COLORS.danger + ';">⚠</span>' : ''}
            </div>`;
          }
        });
        return html;
      }
    },
    series,
    graphic: [
      {
        type: 'line',
        id: 'time-cursor',
        shape: {
          x1: 0,
          y1: 0,
          x2: 0,
          y2: 0
        },
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
          x1: xPos,
          y1: yStart,
          x2: xPos,
          y2: yEnd
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

  const markPoints = dataStore.quenchEvents.map(event => ({
    name: event.sensorId,
    xAxis: event.startTime,
    yAxis: event.peakResistivity,
    itemStyle: {
      color: COLORS.danger
    },
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
    const sensorIndex = series.findIndex(s => s.name === dataStore.quenchEvents[0]?.sensorId);
    if (sensorIndex >= 0) {
      series[sensorIndex].markPoint = {
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
  () => {
    updateTimeCursor();
  }
);

watch(
  () => dataStore.timeSeriesData,
  () => {
    if (chartInstance) {
      const { series } = prepareChartData();
      chartInstance.setOption({ series });
      highlightQuenchPoints();
    }
  },
  { deep: true }
);

watch(
  () => dataStore.quenchEvents,
  () => {
    highlightQuenchPoints();
  },
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
  </div>
</template>

<style scoped>
.resistivity-chart {
  backdrop-filter: blur(8px);
}
</style>
