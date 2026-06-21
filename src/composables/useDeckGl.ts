import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Deck, OrbitView, OrbitController } from '@deck.gl/core';
import { ScatterplotLayer, LineLayer, TextLayer } from '@deck.gl/layers';
import type { ParticleState, SensorInfo } from '@/types';
import { generateCryostatProfile, generateCutSurface, generateBottomSurface } from '@/utils/geometry';
import { CRYOSTAT_CONFIG, COLORS } from '@/types';
import type { ParticlePoolAPI } from '@/utils/particlePool';

interface DeckGlOptions {
  container: HTMLElement | null;
  width: number;
  height: number;
}

const STATIC_LAYER_COUNT = 5;

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

  const staticLayers = ref<any[]>([]);
  const cachedSensors = ref<SensorInfo[]>([]);
  const lastHeatGlowSignature = ref<string>('');

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
    buildStaticLayers();
  }

  function sensorsEqual(a: SensorInfo[], b: SensorInfo[]): boolean {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (a[i].sensorId !== b[i].sensorId) return false;
    }
    return true;
  }

  function buildStaticLayers(sensors?: SensorInfo[]) {
    if (sensors && sensorsEqual(sensors, cachedSensors.value) && staticLayers.value.length > 0) {
      return;
    }
    if (sensors) cachedSensors.value = sensors;

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
      widthUnits: 'pixels',
      updateTriggers: {}
    });

    const cutSurfaceLayer = new LineLayer({
      id: 'cut-surface',
      data: cutSurface,
      getSourcePosition: (d: any) => d[0],
      getTargetPosition: (d: any) => d[1] || d[0],
      getColor: [0, 255, 213, 100],
      getWidth: 1,
      widthUnits: 'pixels',
      updateTriggers: {}
    });

    const bottomSurfaceLayer = new LineLayer({
      id: 'bottom-surface',
      data: bottomSurface,
      getSourcePosition: (d: any) => d[0],
      getTargetPosition: (d: any) => d[1] || d[0],
      getColor: [0, 212, 255, 80],
      getWidth: 1,
      widthUnits: 'pixels',
      updateTriggers: {}
    });

    const axisLayer = createAxisLayer();

    const sensorMarkers = cachedSensors.value.length > 0
      ? new ScatterplotLayer({
          id: 'sensor-markers',
          data: cachedSensors.value,
          getPosition: (d: SensorInfo) => d.position,
          getFillColor: [255, 215, 0, 200],
          getRadius: 0.03,
          radiusUnits: 'meters',
          opacity: 1,
          stroked: true,
          getLineColor: [255, 255, 255, 255],
          getLineWidth: 2,
          lineWidthUnits: 'pixels',
          updateTriggers: {}
        })
      : null;

    const sensorLabels = cachedSensors.value.length > 0
      ? new TextLayer({
          id: 'sensor-labels',
          data: cachedSensors.value.filter((_, i) => i % 4 === 0),
          getPosition: (d: SensorInfo) => [d.position[0], d.position[1] + 0.05, d.position[2]],
          getText: (d: SensorInfo) => d.sensorId,
          getSize: 12,
          sizeUnits: 'pixels',
          getColor: [255, 255, 255, 200],
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'bottom',
          updateTriggers: {}
        })
      : null;

    staticLayers.value = [
      axisLayer,
      outerWallLayer,
      cutSurfaceLayer,
      bottomSurfaceLayer,
      ...(sensorMarkers ? [sensorMarkers] : []),
      ...(sensorLabels ? [sensorLabels] : [])
    ];
  }

  function createAxisLayer() {
    const axisData = [
      { source: [0, 0, 0], target: [1.5, 0, 0], color: [255, 100, 100, 200] },
      { source: [0, 0, 0], target: [0, 1.5, 0], color: [100, 255, 100, 200] },
      { source: [0, 0, 0], target: [0, 0, 1.5], color: [100, 100, 255, 200] }
    ];

    return new LineLayer({
      id: 'axis-lines',
      data: axisData,
      getSourcePosition: (d: any) => d.source,
      getTargetPosition: (d: any) => d.target,
      getColor: (d: any) => d.color,
      getWidth: 2,
      widthUnits: 'pixels',
      updateTriggers: {}
    });
  }

  function createHeatGlowLayer(temperature: number, quenchDetected: boolean, forceRebuild: boolean = false) {
    const sig = `${temperature.toFixed(2)}_${quenchDetected ? 'q' : 'n'}`;
    if (!forceRebuild && sig === lastHeatGlowSignature.value) {
      return null;
    }
    lastHeatGlowSignature.value = sig;

    const intensity = Math.min(1, (temperature - 77) / 20);
    const baseRadius = 0.8 + intensity * 0.3;
    const pulsePhase = Date.now() / 500;
    const pulseFactor = quenchDetected ? 1 + Math.sin(pulsePhase) * 0.2 : 1;

    const heatRingData: number[][] = [];
    for (let i = 0; i < 16; i++) {
      const angle = (i / 16) * Math.PI * 2;
      const radius = baseRadius * pulseFactor;
      heatRingData.push([
        radius * Math.cos(angle),
        -CRYOSTAT_CONFIG.height / 2 + 0.01,
        radius * Math.sin(angle)
      ]);
    }

    const fillColor = quenchDetected
      ? [255, 71, 87, Math.floor(intensity * 100)]
      : [255, 165, 2, Math.floor(intensity * 60)];

    return new ScatterplotLayer({
      id: 'heat-glow',
      data: heatRingData,
      getPosition: (d: any) => d,
      getFillColor: fillColor as any,
      getRadius: 0.2,
      radiusUnits: 'meters',
      opacity: 0.5,
      parameters: {
        blend: true,
        blendFunc: [770, 771]
      },
      updateTriggers: {
        getFillColor: [quenchDetected, intensity]
      }
    } as any);
  }

  function createParticleLayerFromPool(pool: ParticlePoolAPI) {
    const binary = pool.toDeckGlBinary();

    return new ScatterplotLayer({
      id: 'nitrogen-particles',
      data: binary,
      _dataDiff: () => [],
      getPosition: { value: binary.attributes.getPosition.value, size: 3 } as any,
      getFillColor: { value: binary.attributes.getFillColor.value, size: 4 } as any,
      getRadius: { value: binary.attributes.getRadius.value, size: 1 } as any,
      radiusUnits: 'pixels',
      opacity: 1,
      stroked: false,
      filled: true,
      parameters: {
        blend: true,
        blendFunc: [770, 771]
      },
      updateTriggers: {
        getPosition: [binary.attributes.getPosition.value.buffer],
        getFillColor: [binary.attributes.getFillColor.value.buffer],
        getRadius: [binary.attributes.getRadius.value.buffer]
      },
      numInstances: binary.length
    } as any);
  }

  function createParticleLayerLegacy(particles: ParticleState[]) {
    return new ScatterplotLayer({
      id: 'nitrogen-particles',
      data: particles,
      getPosition: (d: ParticleState) => d.position,
      getFillColor: (d: any) => d._color || null,
      getRadius: (d: ParticleState) => d.size * 50,
      radiusUnits: 'pixels',
      opacity: 1,
      stroked: false,
      filled: true,
      parameters: {
        blend: true,
        blendFunc: [770, 771]
      }
    } as any);
  }

  function update(
    particlePoolOrArray: ParticlePoolAPI | ParticleState[],
    sensors: SensorInfo[],
    heatZoneTemp: number,
    quenchDetected: boolean
  ) {
    if (!deckInstance.value) return;

    buildStaticLayers(sensors);

    const particleLayer = (particlePoolOrArray as any).toDeckGlBinary
      ? createParticleLayerFromPool(particlePoolOrArray as ParticlePoolAPI)
      : createParticleLayerLegacy(particlePoolOrArray as ParticleState[]);

    const heatLayer = createHeatGlowLayer(heatZoneTemp, quenchDetected);
    const allLayers = heatLayer
      ? [...staticLayers.value, heatLayer, particleLayer]
      : [...staticLayers.value, particleLayer];

    deckInstance.value.setProps({ layers: allLayers });
  }

  function updateParticlesOnly(pool: ParticlePoolAPI) {
    if (!deckInstance.value) return;
    if (staticLayers.value.length === 0) return;

    const particleLayer = createParticleLayerFromPool(pool);
    const currentLayers = deckInstance.value.props?.layers || [];

    const newLayers = [...currentLayers];
    const particleIdx = newLayers.findIndex((l: any) => l && l.id === 'nitrogen-particles');
    if (particleIdx >= 0) {
      newLayers[particleIdx] = particleLayer;
    } else {
      newLayers.push(particleLayer);
    }

    deckInstance.value.setProps({ layers: newLayers });
  }

  function updateHeatGlow(temperature: number, quenchDetected: boolean) {
    if (!deckInstance.value) return;
    if (staticLayers.value.length === 0) return;

    const heatLayer = createHeatGlowLayer(temperature, quenchDetected, true);
    if (!heatLayer) return;

    const currentLayers = deckInstance.value.props?.layers || [...staticLayers.value];
    const newLayers = [...currentLayers];
    const heatIdx = newLayers.findIndex((l: any) => l && l.id === 'heat-glow');
    if (heatIdx >= 0) {
      newLayers[heatIdx] = heatLayer;
    } else {
      const particleIdx = newLayers.findIndex((l: any) => l && l.id === 'nitrogen-particles');
      if (particleIdx >= 0) {
        newLayers.splice(particleIdx, 0, heatLayer);
      } else {
        newLayers.push(heatLayer);
      }
    }

    deckInstance.value.setProps({ layers: newLayers });
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
    staticLayers.value = [];
    cachedSensors.value = [];
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
    updateParticlesOnly,
    updateHeatGlow,
    resize,
    destroy
  };
}
