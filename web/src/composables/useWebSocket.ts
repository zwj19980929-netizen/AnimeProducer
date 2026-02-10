import { ref, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export interface WebSocketMessage {
  type: string
  [key: string]: unknown
}

export interface UseWebSocketOptions {
  onMessage?: (message: WebSocketMessage) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Event) => void
  reconnect?: boolean
  reconnectInterval?: number
  maxReconnectAttempts?: number
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const {
    onMessage,
    onOpen,
    onClose,
    onError,
    reconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5
  } = options

  const ws = ref<WebSocket | null>(null)
  const isConnected = ref(false)
  const reconnectAttempts = ref(0)
  const lastMessage: Ref<WebSocketMessage | null> = ref(null)

  let reconnectTimer: number | null = null
  let pingTimer: number | null = null

  function getWebSocketUrl(path: string): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = import.meta.env.VITE_WS_HOST || window.location.host
    return `${protocol}//${host}/ws${path}`
  }

  function connect(path: string) {
    if (ws.value?.readyState === WebSocket.OPEN) {
      return
    }

    const url = getWebSocketUrl(path)
    ws.value = new WebSocket(url)

    ws.value.onopen = () => {
      isConnected.value = true
      reconnectAttempts.value = 0
      onOpen?.()
      startPing()
    }

    ws.value.onclose = () => {
      isConnected.value = false
      stopPing()
      onClose?.()

      if (reconnect && reconnectAttempts.value < maxReconnectAttempts) {
        reconnectTimer = window.setTimeout(() => {
          reconnectAttempts.value++
          connect(path)
        }, reconnectInterval)
      }
    }

    ws.value.onerror = (error) => {
      onError?.(error)
    }

    ws.value.onmessage = (event) => {
      if (event.data === 'pong') {
        return
      }

      try {
        const message = JSON.parse(event.data) as WebSocketMessage
        lastMessage.value = message
        onMessage?.(message)
      } catch {
        console.error('Failed to parse WebSocket message:', event.data)
      }
    }
  }

  function disconnect() {
    stopPing()
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    isConnected.value = false
  }

  function send(data: unknown) {
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }

  function startPing() {
    stopPing()
    pingTimer = window.setInterval(() => {
      if (ws.value?.readyState === WebSocket.OPEN) {
        ws.value.send('ping')
      }
    }, 30000) // Ping every 30 seconds
  }

  function stopPing() {
    if (pingTimer) {
      clearInterval(pingTimer)
      pingTimer = null
    }
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    ws,
    isConnected,
    lastMessage,
    reconnectAttempts,
    connect,
    disconnect,
    send
  }
}

/**
 * Hook for subscribing to project updates via WebSocket
 */
export function useProjectWebSocket(
  projectId: string,
  onUpdate?: (message: WebSocketMessage) => void
) {
  const { isConnected, lastMessage, connect, disconnect } = useWebSocket({
    onMessage: onUpdate,
    reconnect: true
  })

  function startListening() {
    connect(`/projects/${projectId}`)
  }

  function stopListening() {
    disconnect()
  }

  return {
    isConnected,
    lastMessage,
    startListening,
    stopListening
  }
}

/**
 * Hook for subscribing to job updates via WebSocket
 */
export function useJobWebSocket(
  jobId: string,
  onUpdate?: (message: WebSocketMessage) => void
) {
  const { isConnected, lastMessage, connect, disconnect } = useWebSocket({
    onMessage: onUpdate,
    reconnect: true
  })

  function startListening() {
    connect(`/jobs/${jobId}`)
  }

  function stopListening() {
    disconnect()
  }

  return {
    isConnected,
    lastMessage,
    startListening,
    stopListening
  }
}
