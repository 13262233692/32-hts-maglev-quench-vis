import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Deck, OrbitView, OrbitController } from '@deck.gl/core';
import { ScatterplotLayer, LineLayer, TextLayer } from '@deck.gl/layers';
import type { ParticleState, SensorInfo } from '@/types';
import { temperatureToColor } from '@/utils/color';
import { generateCryostatProfile, generateCutSurface, generateBottomSurface } from '@/utils/geometry';
import { CRYOSTAT_CONFIG, COLORS } from '@/types';

interface DeckGlOptions {
  container: HTMLElement | null;
  width: number;
  height: number;
}

export function useDeckGl(options: DeckGlOptions) {
  const deckInstance = ref<any>(null);
  const viewState = ref<any>({
    target: [0, 0, 0],
    zoom: 2,
    rotationX: -30,
    rotationOrbit: 45,
    minZoom: 1,
    maxZoom: 6
  });

  function initialize() {
    if (!options.container || !options.width || !options.height) return;

    const deckProps: any = {
      canvas: 'cryostat-canvas',
      width: options.width,
      height: options.height,
      controller: {
        type: OrbitController,
        scrollZoom: true,
        dragPan: false,
        dragRotate: true,
        touchRotate: true
      },
      initialViewState: viewState.value,
      views: [
        new OrbitView()
      ],
      layers: [],
      parameters: {
        clearColor: [10, 22, 40, 255],
        depthTest: true,
        blend: true,
        blendFunc: [770, 771, 1, 771]
      },
      onViewStateChange: ({ viewState: newViewState }: any) => {
        viewState.value = newViewState;
      }
    };

    deckInstance.value = new Deck(deckProps);
  }

  function createLayers(
    particles: ParticleState[],
    sensors: SensorInfo[],
    heatZoneTemp: number = 77,
    quenchDetected: boolean = false
  ) {
    const cryostatProfiles = generateCryostatProfile();
    const cutSurface = generateCutSurface();
    const bottomSurface = generateBottomSurface();

    const outerWallLayer = new LineLayer({
      id: 'cryostat-outer-wall',
      data: cryostatProfiles,
      getSourcePosition: (d: any) => d[0],
      getTargetPosition: (d: any) => d[1] || d[0],
      getColor: [0, 212, 255, 150],
      getWidth: 2,
      widthUnits: 'pixels'
    });

    const cutSurfaceLayer = new LineLayer({
      id: 'cut-surface',
      data: cutSurface,
      getSourcePosition: (d: any) => d[0],
      getTargetPosition: (d: any) => d[1] || d[0],
      getColor: [0, 255, 213, 100],
      getWidth: 1,
      widthUnits: 'pixels'
    });

    const bottomSurfaceLayer = new LineLayer({
      id: 'bottom-surface',
      data: bottomSurface,
      getSourcePosition: (d: any) => d[0],
      getTargetPosition: (d: any) => d[1] || d[0],
      getColor: [0, 212, 255, 80],
      getWidth: 1,
      widthUnits: 'pixels'
    });

    const particleLayer = new ScatterplotLayer({
      id: 'nitrogen-particles',
      data: particles,
      getPosition: (d: ParticleState) => d.position,
      getFillColor: (d: ParticleState) => temperatureToColor(d.temperature),
      getRadius: (d: ParticleState) => d.size * 50,
      radiusUnits: 'pixels',
      opacity: 1,
      stroked: false,
      filled: true,
      parameters: {
        blend: true,
        blendFunc: [770, 771]
      }
    });

    const sensorLayer = new ScatterplotLayer({
      id: 'sensor-markers',
      data: sensors,
      getPosition: (d: SensorInfo) => d.position,
      getFillColor: (d: SensorInfo) => [255, 215, 0, 200],
      getRadius: 0.03,
      radiusUnits: 'meters',
      opacity: 1,
      stroked: true,
      getLineColor: [255, 255, 255, 255],
      getLineWidth: 2,
      lineWidthUnits: 'pixels'
    });

    const sensorLabels = new TextLayer({
      id: 'sensor-labels',
      data: sensors.filter((_, i) => i % 4 === 0),
      getPosition: (d: SensorInfo) => [d.position[0], d.position[1] + 0.05, d.position[2]],
      getText: (d: SensorInfo) => d.sensorId,
      getSize: 12,
      sizeUnits: 'pixels',
      getColor: [255, 255, 255, 200],
      getTextAnchor: 'middle',
      getAlignmentBaseline: 'bottom'
    });

    const axisLayer = createAxisLayer();
    const heatGlowLayer = createHeatGlowLayer(heatZoneTemp, quenchDetected);

    return [
      axisLayer,
      outerWallLayer,
      cutSurfaceLayer,
      bottomSurfaceLayer,
      particleLayer,
      sensorLayer,
      sensorLabels,
      heatGlowLayer
    ];
  }

  function createAxisLayer() {
    const axisData = [
      { source: [0, 0, 0], target: [1.5, 0, 0], color: [255, 100, 100, 200], label: 'X' },
      { source: [0, 0, 0], target: [0, 1.5, 0], color: [100, 255, 100, 200], label: 'Y' },
      { source: [0, 0, 0], target: [0, 0, 1.5], color: [100, 100, 255, 200], label: 'Z' }
    ];

    return new LineLayer({
      id: 'axis-lines',
      data: axisData,
      getSourcePosition: (d: any) => d.source,
      getTargetPosition: (d: any) => d.target,
      getColor: (d: any) => d.color,
      getWidth: 2,
      widthUnits: 'pixels'
    });
  }

  function createHeatGlowLayer(temperature: number, quenchDetected: boolean) {
    const intensity = Math.min(1, (temperature - 77) / 20);
    const baseRadius = 0.8 + intensity * 0.3;
    const pulsePhase = Date.now() / 500;
    const pulseFactor = quenchDetected ? 1 + Math.sin(pulsePhase) * 0.2 : 1;

    const heatRingData = [];
    for (let i = 0; i < 16; i++) {
      const angle = (i / 16) * Math.PI * 2;
      const radius = baseRadius * pulseFactor;
      heatRingData.push({
        position: [
          radius * Math.cos(angle),
          -CRYOSTAT_CONFIG.height / 2 + 0.01,
          radius * Math.sin(angle)
        ],
        intensity
      });
    }

    return new ScatterplotLayer({
      id: 'heat-glow',
      data: heatRingData,
      getPosition: (d: any) => d.position,
      getFillColor: () => {
        if (quenchDetected) {
          return [255, 71, 87, Math.floor(intensity * 100)];
        }
        return [255, 165, 2, Math.floor(intensity * 60)];
      },
      getRadius: 0.2,
      radiusUnits: 'meters',
      opacity: 0.5,
      parameters: {
        blend: true,
        blendFunc: [770, 771]
      }
    });
  }

  function update(particles: ParticleState[], sensors: SensorInfo[], heatZoneTemp: number, quenchDetected: boolean) {
    if (!deckInstance.value) return;

    const layers = createLayers(particles, sensors, heatZoneTemp, quenchDetected);
    deckInstance.value.setProps({ layers });
  }

  function resize(width: number, height: number) {
    if (!deckInstance.value) return;
    deckInstance.value.setProps({ width, height });
  }

  function destroy() {
    if (deckInstance.value) {
      deckInstance.value.finalize();
      deckInstance.value = null;
    }
  }

  watch(
    () => [options.width, options.height],
    () => {
      resize(options.width, options.height);
    }
  );

  onMounted(() => {
    initialize();
  });

  onUnmounted(() => {
    destroy();
  });

  return {
    deckInstance,
    viewState,
    initialize,
    update,
    resize,
    destroy
  };
}
