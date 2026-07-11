/**
 * Base API service with common HTTP methods.
 * @module services/api
 */

/**
 * Get the API base URL from runtime config.
 * @returns The API base URL.
 */
function getBaseUrl(): string {
  const config = useRuntimeConfig()
  return config.public.apiBase
}

/**
 * Make an authenticated API request.
 * @param endpoint - API endpoint (starting with /).
 * @param options - Fetch options.
 * @returns Parsed response data.
 * @throws If the request fails.
 */
async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const userStore = useUserStore()

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(userStore.token && { Authorization: `Bearer ${userStore.token}` }),
    ...options.headers,
  }

  const response = await fetch(`${getBaseUrl()}${endpoint}`, { ...options, headers })

  if (!response.ok) {
    const errorText = await response.text().catch(() => '')
    let errorMessage = `API request failed: ${response.statusText}`
    if (errorText) {
      try {
        const errorJson = JSON.parse(errorText)
        errorMessage = errorJson.detail || errorJson.message || errorMessage
      } catch {
        errorMessage = errorText || errorMessage
      }
    }
    throw new Error(errorMessage)
  }

  const text = await response.text()
  if (!text || text.trim() === '') {
    return undefined as T
  }
  try {
    return JSON.parse(text)
  } catch {
    return text as T
  }
}

/**
 * API service with common HTTP methods.
 */
export const api = {
  /**
   * GET request.
   * @param endpoint - API endpoint.
   * @param options - Optional query params.
   * @returns Response data.
   */
  get<T>(
    endpoint: string,
    options?: { params?: Record<string, string | number | boolean | null | undefined> },
  ): Promise<T> {
    let url = endpoint
    if (options?.params) {
      const params = new URLSearchParams()
      Object.entries(options.params).forEach(([key, value]) => {
        if (value !== null && value !== undefined) {
          params.append(key, String(value))
        }
      })
      const queryString = params.toString()
      if (queryString) {
        url += `?${queryString}`
      }
    }
    return request<T>(url, { method: 'GET' })
  },

  /**
   * POST request.
   * @param endpoint - API endpoint.
   * @param data - Request body.
   * @returns Response data.
   */
  post<T>(endpoint: string, data?: unknown): Promise<T> {
    return request<T>(endpoint, { method: 'POST', body: JSON.stringify(data ?? {}) })
  },

  /**
   * PATCH request.
   * @param endpoint - API endpoint.
   * @param data - Request body.
   * @returns Response data.
   */
  patch<T>(endpoint: string, data: unknown): Promise<T> {
    return request<T>(endpoint, { method: 'PATCH', body: JSON.stringify(data) })
  },

  /**
   * PUT request.
   * @param endpoint - API endpoint.
   * @param data - Request body.
   * @returns Response data.
   */
  put<T>(endpoint: string, data?: unknown): Promise<T> {
    return request<T>(endpoint, { method: 'PUT', body: JSON.stringify(data ?? {}) })
  },

  /**
   * DELETE request.
   * @param endpoint - API endpoint.
   * @returns Response data.
   */
  delete<T = void>(endpoint: string): Promise<T> {
    return request<T>(endpoint, { method: 'DELETE' })
  },
}
