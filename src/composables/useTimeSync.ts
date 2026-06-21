import { ref, onMounted, onUnmounted, watch } from 'vue';
import { useDataStore } from '@/stores/dataStore';

export function useTimeSync(updateInterval: number = 50) {
  const dataStore = useDataStore();
  const animationFrameId = ref<number | null>(null);
  const lastUpdateTime = ref(0);

  function startAnimationLoop() {
    function update(currentTime: number) {
      if (dataStore.isPlaying) {
        const deltaTime = (currentTime - lastUpdateTime.value) / 1000;
        if (deltaTime > updateInterval / 1000) {
          const newTime = dataStore.currentTime + deltaTime * dataStore.playbackSpeed;
          
          if (newTime >= dataStore.timeRange.endTime) {
            dataStore.setCurrentTime(dataStore.timeRange.startTime);
          } else {
            dataStore.setCurrentTime(newTime);
          }
          
          lastUpdateTime.value = currentTime;
        }
      }
      
      animationFrameId.value = requestAnimationFrame(update);
    }
    
    lastUpdateTime.value = performance.now();
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
    async (newTime) => {
      await Promise.all([
        dataStore.fetchSummary(newTime),
        dataStore.fetchParticles(newTime, 2500)
      ]);
    },
    { flush: 'post' }
  );

  onMounted(() => {
    startAnimationLoop();
  });

  onUnmounted(() => {
    stopAnimationLoop();
  });

  return {
    startAnimationLoop,
    stopAnimationLoop
  };
}
