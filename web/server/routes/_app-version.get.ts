/**
 * Report the running server's build id so the web PWA can detect a new deployment
 * (iOS home-screen apps never reload on their own — the client polls this).
 */
export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event)
  return { buildId: config.public.buildId }
})
