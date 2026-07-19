<template>
  <div />
</template>

<script lang="ts" setup>
import { onMounted } from 'vue'

/**
 * Legacy projects route — project management lives in the dashboard drawer.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const router = useRouter()

onMounted(() => {
  router.replace('/dashboard')
})
</script>
