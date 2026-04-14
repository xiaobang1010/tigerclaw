import { ref, computed, watch } from 'vue'

const SESSIONS_KEY = 'tigerclaw_sessions'
const ACTIVE_KEY = 'tigerclaw_active_session'

function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).substring(2, 8)
}

function loadFromStorage(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch {
    return fallback
  }
}

export function useSessions() {
  const sessions = ref(
    Array.isArray(loadFromStorage(SESSIONS_KEY, []))
      ? loadFromStorage(SESSIONS_KEY, [])
      : []
  )
  const activeSessionId = ref(loadFromStorage(ACTIVE_KEY, null))

  const currentSession = computed(() =>
    sessions.value.find((s) => s.id === activeSessionId.value) || null
  )

  const currentMessages = computed(() =>
    currentSession.value ? currentSession.value.messages : []
  )

  function sortSessions() {
    sessions.value.sort((a, b) => b.updatedAt - a.updatedAt)
  }

  function createSession() {
    const session = {
      id: generateId(),
      title: '新对话',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now()
    }
    sessions.value.unshift(session)
    activeSessionId.value = session.id
    return session.id
  }

  function switchSession(id) {
    const exists = sessions.value.some((s) => s.id === id)
    if (exists) {
      activeSessionId.value = id
    }
  }

  function deleteSession(id) {
    const index = sessions.value.findIndex((s) => s.id === id)
    if (index === -1) return

    sessions.value.splice(index, 1)

    if (activeSessionId.value === id) {
      if (sessions.value.length > 0) {
        activeSessionId.value = sessions.value[0].id
      } else {
        activeSessionId.value = null
      }
    }
  }

  function addMessage(sessionId, message) {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (!session) return

    session.messages.push({
      ...message,
      timestamp: message.timestamp || new Date().toISOString()
    })
    session.updatedAt = Date.now()

    if (
      message.role === 'user' &&
      session.title === '新对话' &&
      session.messages.filter((m) => m.role === 'user').length === 1
    ) {
      session.title = message.content.substring(0, 20)
    }

    sortSessions()
  }

  function updateSessionTitle(sessionId, title) {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (session) {
      session.title = title
      session.updatedAt = Date.now()
      sortSessions()
    }
  }

  watch(
    () => sessions.value,
    (val) => {
      localStorage.setItem(SESSIONS_KEY, JSON.stringify(val))
    },
    { deep: true }
  )

  watch(
    () => activeSessionId.value,
    (val) => {
      localStorage.setItem(ACTIVE_KEY, JSON.stringify(val))
    }
  )

  return {
    sessions,
    activeSessionId,
    currentSession,
    currentMessages,
    createSession,
    switchSession,
    deleteSession,
    addMessage,
    updateSessionTitle
  }
}
