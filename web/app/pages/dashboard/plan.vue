<template>
  <div class="flex items-center justify-center py-20 text-sm text-[var(--app-ink-soft)]">
    Redirection vers le compositeur…
  </div>
</template>

<script lang="ts" setup>
/**
 * Legacy planner route — merged into the night composer.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const router = useRouter()

onMounted(() => {
  router.replace('/dashboard/compose')
})
</script>
