import { ref, onMounted, onUnmounted, watch } from 'vue';
import { useDataStore } from '@/stores/dataStore';

export function useTimeSync(updateInterval: number = 16) {
  const dataStore = useDataStore();
  const animationFrameId = ref<number | null>(null);
  const lastUpdateTime = ref(0);
  const lastFrameTime = ref(0);

  function startAnimationLoop() {
    function update(currentTime: number) {
      const dt = lastFrameTime.value ? (currentTime - lastFrameTime.value) / 1000 : 0.016;
      lastFrameTime.value = currentTime;

      if (dataStore.isPlaying) {
        const deltaSim = (currentTime - lastUpdateTime.value) / 1000;
        if (deltaSim > updateInterval / 1000) {
          const newTime = dataStore.currentTime + deltaSim * dataStore.playbackSpeed;
          const clampedTime = newTime >= dataStore.timeRange.endTime
            ? dataStore.timeRange.startTime
            : newTime;

          dataStore.setCurrentTime(clampedTime);
          dataStore.fetchSummary(clampedTime);
          dataStore.fetchParticles(clampedTime, 2500);
          lastUpdateTime.value = currentTime;
        }
      }

      if (dataStore.isPlaying || dataStore.boilingIntensity > 0) {
        dataStore.advanceParticles(dt);
      }

      animationFrameId.value = requestAnimationFrame(update);
    }

    lastUpdateTime.value = performance.now();
    lastFrameTime.value = performance.now();
    animationFrameId.value = requestAnimationFrame(update);
  }

  function stopAnimationLoop() {
    if (animationFrameId.value !== null) {
      cancelAnimationFrame(animationFrameId.value);
      animationFrameId.value = null;
    }
  }

  watch(
    () => dataStore.currentTime,
    (newTime) => {
      dataStore.fetchSummary(newTime, true);
      dataStore.fetchParticles(newTime, 2500, true);
    },
    { flush: 'post' }
  );

  onMounted(() => {
    startAnimationLoop();
  });

  onUnmounted(() => {
    stopAnimationLoop();
    dataStore.dispose();
  });

  return {
    startAnimationLoop,
    stopAnimationLoop
  };
}
