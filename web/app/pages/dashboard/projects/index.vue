<template>
  <div class="flex items-center justify-center py-20 text-sm text-[var(--app-ink-soft)]">
    Redirection vers le compositeur…
  </div>
</template>

<script lang="ts" setup>
/**
 * Legacy projects route — project management now lives in the night composer
 * (drawers for create / settings / paths). Kept as a redirect for old links.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const router = useRouter()

onMounted(() => {
  router.replace('/dashboard/compose')
})
</script>
