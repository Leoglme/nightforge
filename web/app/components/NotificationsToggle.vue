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

      <template v-if="supported">
        <div v-if="subscribed" class="flex shrink-0 items-center gap-1.5">
          <UButton size="xs" color="neutral" variant="ghost" :loading="testing" @click="test">
            {{ t('notifications.test') }}
          </UButton>
          <UButton size="xs" color="neutral" variant="outline" :loading="busy" @click="disable">
            {{ t('notifications.disable') }}
          </UButton>
        </div>
        <UButton v-else size="xs" color="primary" icon="i-lucide-bell" :loading="busy" @click="enable">
          {{ t('notifications.enable') }}
        </UButton>
      </template>
      <span v-else class="shrink-0 text-xs text-[var(--app-ink-soft)]">{{ t('notifications.unavailable') }}</span>
    </div>

    <p class="mt-2 text-xs text-[var(--app-ink-soft)]">{{ hint }}</p>
  </section>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'

/**
 * Enable / disable mobile push notifications (session finished, waiting, error, quota).
 */
const { t } = useI18n()
const toast = useToast()
const { supported, subscribed, busy, error, enable, disable, sendTest } = useWebPush()

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
  return t('notifications.hintDefault')
})

/**
 * Send a test notification and toast the result.
 * @returns Nothing.
 */
async function test(): Promise<void> {
  testing.value = true
  try {
    await sendTest()
    toast.add({ title: t('notifications.testSent'), color: 'success' })
  } catch {
    toast.add({ title: t('notifications.testFailed'), color: 'error' })
  } finally {
    testing.value = false
  }
}
</script>
