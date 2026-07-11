import { defineStore } from 'pinia'
import type { Ref } from 'vue'
import { computed, ref } from 'vue'
import type { LoginCredentials, User } from '~/types'
import * as authService from '~/services/authService'

/**
 * Pinia store for user authentication and profile management.
 * @module stores/user
 */

export const useUserStore = defineStore('user', () => {
  const user: Ref<User | null> = ref(null)
  const token: Ref<string | null> = ref(null)
  const isLoading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)
  const lastValidationTime: Ref<number | null> = ref(null)

  const VALIDATION_CACHE_TIME = 30000

  const isAuthenticated = computed(() => user.value !== null && token.value !== null)
  const userName = computed(() => user.value?.name ?? '')
  const userEmail = computed(() => user.value?.email ?? '')

  /**
   * Login with credentials and persist the session.
   * @param credentials - Login credentials.
   * @returns Nothing.
   * @throws If login fails.
   */
  async function login(credentials: LoginCredentials): Promise<void> {
    try {
      isLoading.value = true
      error.value = null
      const tokenResponse = await authService.login(credentials)
      token.value = tokenResponse.access_token
      user.value = await authService.getCurrentUser(token.value)
      if (import.meta.client) {
        localStorage.setItem('token', token.value)
        localStorage.setItem('user', JSON.stringify(user.value))
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Échec de la connexion'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Log out and clear the session.
   * @returns Nothing.
   */
  function logout(): void {
    user.value = null
    token.value = null
    lastValidationTime.value = null
    if (import.meta.client) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    }
  }

  /**
   * Initialize the store from localStorage.
   * @returns Nothing.
   */
  function initializeAuth(): void {
    if (!import.meta.client) {
      return
    }
    try {
      const storedToken = localStorage.getItem('token')
      const storedUser = localStorage.getItem('user')
      if (storedToken && storedUser) {
        token.value = storedToken
        user.value = JSON.parse(storedUser)
      }
    } catch {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      token.value = null
      user.value = null
    }
  }

  /**
   * Validate the session by calling /me (cached briefly).
   * @returns True if authenticated.
   */
  async function validateAuth(): Promise<boolean> {
    if (typeof window === 'undefined') {
      return false
    }
    const storedToken = localStorage.getItem('token')
    if (!storedToken) {
      token.value = null
      user.value = null
      lastValidationTime.value = null
      return false
    }
    const now = Date.now()
    if (lastValidationTime.value && now - lastValidationTime.value < VALIDATION_CACHE_TIME) {
      return token.value !== null && user.value !== null
    }
    try {
      token.value = storedToken
      const userData = await authService.getCurrentUser(storedToken)
      user.value = userData
      localStorage.setItem('user', JSON.stringify(userData))
      localStorage.setItem('token', storedToken)
      lastValidationTime.value = now
      return true
    } catch {
      logout()
      return false
    }
  }

  return {
    user,
    token,
    isLoading,
    error,
    isAuthenticated,
    userName,
    userEmail,
    login,
    logout,
    initializeAuth,
    validateAuth,
  }
})
