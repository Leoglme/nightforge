/**
 * Authentication middleware — protects routes that require a session.
 * @module middleware/auth
 */
export default defineNuxtRouteMiddleware(async () => {
  const userStore = useUserStore()

  if (import.meta.client) {
    if (!userStore.isAuthenticated) {
      userStore.initializeAuth()
    }
    const isValid = await userStore.validateAuth()
    if (!isValid) {
      return navigateTo('/login')
    }
  }
})
