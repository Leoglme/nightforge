/**
 * Initialize the user store from localStorage on app startup (client-only).
 */
export default defineNuxtPlugin(() => {
  const userStore = useUserStore()
  userStore.initializeAuth()
})
