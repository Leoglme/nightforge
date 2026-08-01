<template>
  <section class="app-card p-3 sm:p-4">
    <div class="flex items-center justify-between gap-3">
      <span class="flex min-w-0 items-center gap-2">
        <UIcon
          :name="subscribed ? 'i-lucide-bell-ring' : 'i-lucide-bell'"
          :class="subscribed ? 'text-[var(--app-accent)]' : 'text-[var(--app-ink-soft)]'"
          class="h-4 w-4 shrink-0"
        />
        <span class="truncate text-sm font-medium text-[var(--app-ink)]">{{ t('notifications.title') }}</span>
      </span>

      <div v-if="supported" class="flex shrink-0 items-center gap-2">
        <UButton v-if="subscribed" size="xs" color="neutral" variant="ghost" :loading="testing" @click="test">
          {{ t('notifications.test') }}
        </UButton>
        <USwitch :model-value="subscribed" :disabled="busy" @update:model-value="toggle" />
      </div>
      <span v-else class="shrink-0 text-xs text-[var(--app-ink-soft)]">{{ t('notifications.unavailable') }}</span>
    </div>

    <p class="mt-2 text-xs text-[var(--app-ink-soft)]">{{ hint }}</p>
  </section>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'

/**
 * Notifications switch (dashboard) — enable/disable mobile push for session events.
 * Notifications auto-enable once permission is granted; this switch turns them off temporarily.
 */
const { t } = useI18n()
const toast = useToast()
const { supported, subscribed, busy, error, toggle, sendTest } = useWebPush()

const testing = ref(false)

const hint = computed(() => {
  if (!supported.value) {
    return t('notifications.hintInstall')
  }
  if (error.value === 'permission') {
    return t('notifications.errorPermission')
  }
  if (error.value === 'not-configured') {
    return t('notifications.errorConfig')
  }
  return subscribed.value ? t('notifications.hintOn') : t('notifications.hintDefault')
})

/**
 * Send a test notification and toast the result.
 * @returns Nothing.
 */
async function test(): Promise<void> {
  testing.value = true
  try {
    const result = await sendTest()
    if (result.subscriptions === 0) {
      toast.add({ title: t('notifications.testNoDevice'), color: 'warning' })
    } else if (result.failed > 0) {
      toast.add({
        title: t('notifications.testRejected'),
        description: result.detail ?? undefined,
        color: 'error',
      })
    } else {
      toast.add({ title: t('notifications.testDelivered', { n: result.delivered }), color: 'success' })
    }
  } catch {
    toast.add({ title: t('notifications.testFailed'), color: 'error' })
  } finally {
    testing.value = false
  }
}
</script>
