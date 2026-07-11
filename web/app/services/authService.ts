import type { LoginCredentials, TokenResponse, User } from '~/types'

/**
 * Authentication service for user management.
 * @module services/authService
 */

/**
 * Get the API base URL.
 * @returns The API base URL.
 */
function getApiUrl(): string {
  const config = useRuntimeConfig()
  return config.public.apiBase
}

/**
 * Login a user.
 * @param credentials - Login credentials.
 * @returns The token response.
 * @throws If login fails.
 */
export async function login(credentials: LoginCredentials): Promise<TokenResponse> {
  const response = await fetch(`${getApiUrl()}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(credentials),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Login failed' }))
    throw new Error(error.detail || 'Échec de la connexion')
  }
  return response.json()
}

/**
 * Get the current authenticated user.
 * @param token - JWT token.
 * @returns The current user.
 * @throws If the request fails.
 */
export async function getCurrentUser(token: string): Promise<User> {
  const response = await fetch(`${getApiUrl()}/api/v1/auth/me`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  })
  if (!response.ok) {
    throw new Error("Impossible de récupérer l'utilisateur")
  }
  return response.json()
}
