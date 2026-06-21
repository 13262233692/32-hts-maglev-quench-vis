import { ref, onUnmounted } from 'vue';
import type { SummaryStats, ParticleState } from '@/types';

interface WebSocketMessage {
  type: string;
  timestamp: number;
  stats: SummaryStats;
  particles: ParticleState[];
}

export function useWebSocket(url: string = 'ws://localhost:8000/ws/stream') {
  const socket = ref<WebSocket | null>(null);
  const isConnected = ref(false);
  const lastMessage = ref<WebSocketMessage | null>(null);
  const error = ref<string | null>(null);

  function connect() {
    try {
      socket.value = new WebSocket(url);
      
      socket.value.onopen = () => {
        isConnected.value = true;
        error.value = null;
      };
      
      socket.value.onmessage = (event) => {
        try {
          lastMessage.value = JSON.parse(event.data);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };
      
      socket.value.onerror = (event) => {
        error.value = 'WebSocket connection error';
        console.error('WebSocket error:', event);
      };
      
      socket.value.onclose = () => {
        isConnected.value = false;
        setTimeout(() => {
          if (!isConnected.value) {
            connect();
          }
        }, 3000);
      };
    } catch (e) {
      error.value = 'Failed to create WebSocket connection';
      console.error(e);
    }
  }

  function send(message: Record<string, unknown>) {
    if (socket.value && socket.value.readyState === WebSocket.OPEN) {
      socket.value.send(JSON.stringify(message));
    }
  }

  function play(speed: number = 1) {
    send({ action: 'play', speed });
  }

  function pause() {
    send({ action: 'pause' });
  }

  function seek(timestamp: number) {
    send({ action: 'seek', timestamp });
  }

  function setSpeed(speed: number) {
    send({ action: 'set_speed', speed });
  }

  function disconnect() {
    if (socket.value) {
      socket.value.close();
      socket.value = null;
    }
    isConnected.value = false;
  }

  onUnmounted(() => {
    disconnect();
  });

  return {
    isConnected,
    lastMessage,
    error,
    connect,
    disconnect,
    send,
    play,
    pause,
    seek,
    setSpeed
  };
}
