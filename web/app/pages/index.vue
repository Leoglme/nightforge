<template>
  <div class="app-theme flex min-h-screen items-center justify-center">
    <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
  </div>
</template>

<script lang="ts" setup>
/**
 * Entry redirect — send to the dashboard (or login via middleware).
 */
onMounted(() => {
  navigateTo('/dashboard')
})
</script>
