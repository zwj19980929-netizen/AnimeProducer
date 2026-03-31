import { reactive } from 'vue'

import { api, TOKEN_STORAGE_KEY } from '@/lib/api'
import type { AuthBootstrap, TokenResponse, UserInfo } from '@/types/workbench'

interface AuthState {
  token: string | null
  user: UserInfo | null
  bootstrap: AuthBootstrap | null
  initialized: boolean
}

export const authState = reactive<AuthState>({
  token: window.localStorage.getItem(TOKEN_STORAGE_KEY),
  user: null,
  bootstrap: null,
  initialized: false
})

export function setSessionToken(token: string | null) {
  authState.token = token
  if (token) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY)
  }
}

export async function initializeAuthState() {
  if (authState.initialized) {
    return
  }

  authState.bootstrap = await api.getAuthBootstrap()

  if (authState.token) {
    try {
      authState.user = await api.getCurrentUser()
    } catch {
      setSessionToken(null)
      authState.user = null
    }
  }

  authState.initialized = true
}

export async function applyTokenResponse(payload: TokenResponse) {
  setSessionToken(payload.access_token)
  authState.user = await api.getCurrentUser()
}

export function clearAuthState() {
  setSessionToken(null)
  authState.user = null
}
