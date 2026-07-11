import type { LoginCredentials } from '~/types'

/**
 * Composable for authentication operations.
 * @module composables/useAuth
 */

/**
 * Use the authentication composable.
 * @returns Authentication methods and reactive state.
 */
export function useAuth() {
  const userStore = useUserStore()
  const router = useRouter()
  const toast = useToast()

  const login = async (credentials: LoginCredentials): Promise<void> => {
    try {
      await userStore.login(credentials)
      router.push('/dashboard')
    } catch (error) {
      toast.add({ title: error instanceof Error ? error.message : 'Échec de la connexion', color: 'error' })
      throw error
    }
  }

  const logout = (): void => {
    userStore.logout()
    router.push('/login')
  }

  return {
    login,
    logout,
    isAuthenticated: computed(() => userStore.isAuthenticated),
    isLoading: computed(() => userStore.isLoading),
    user: computed(() => userStore.user),
  }
}
