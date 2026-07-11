<template>
  <div class="app-theme flex min-h-screen items-center justify-center p-4">
    <UCard class="w-full max-w-sm">
      <template #header>
        <div class="flex items-center gap-2">
          <UIcon name="i-lucide-moon-star" class="text-[var(--app-accent)]" />
          <h1 class="app-page-title">{{ t('login.title') }}</h1>
        </div>
      </template>

      <form class="flex flex-col gap-4" @submit.prevent="onSubmit">
        <UFormField :label="t('login.email')">
          <UInput v-model="email" type="email" autocomplete="email" required />
        </UFormField>
        <UFormField :label="t('login.password')">
          <UInput v-model="password" type="password" autocomplete="current-password" required />
        </UFormField>
        <UButton type="submit" color="primary" block :loading="isLoading">
          {{ t('login.submit') }}
        </UButton>
      </form>
    </UCard>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'

/**
 * Login page.
 */
definePageMeta({ layout: false })

const { t } = useI18n()
const { login, isLoading } = useAuth()

const email = ref('')
const password = ref('')

/**
 * Submit the login form.
 * @returns Nothing.
 */
async function onSubmit(): Promise<void> {
  try {
    await login({ email: email.value, password: password.value })
  } catch {
    // Errors are surfaced via toast in useAuth.
  }
}
</script>
