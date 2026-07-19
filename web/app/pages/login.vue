<template>
  <div class="app-theme relative min-h-dvh">
    <div class="app-grain"></div>

    <div class="flex min-h-dvh">
      <!-- Poster panel (desktop only, right side) -->
      <aside class="relative hidden overflow-hidden bg-[var(--app-bg)] lg:order-2 lg:flex lg:flex-1 lg:flex-col">
        <!-- Radial glow -->
        <div
          class="pointer-events-none absolute inset-0"
          :style="{
            background:
              'radial-gradient(120% 90% at 80% 10%, var(--app-accent-soft) 0%, transparent 55%), radial-gradient(90% 70% at 15% 95%, rgba(133,168,200,0.10) 0%, transparent 60%)',
          }"
        ></div>

        <!-- Monumental moon mark in ceremonial slow spin -->
        <span
          class="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 select-none"
          aria-hidden="true"
        >
          <UIcon
            name="i-lucide-moon-star"
            class="auth-spin-slow block text-[30rem] text-[var(--app-accent)] opacity-[0.10]"
          />
        </span>

        <!-- Stacked words, centered like a poster -->
        <div class="relative z-10 flex flex-1 items-center justify-center px-10 text-center">
          <div>
            <h2
              class="text-[4.25rem] leading-[1.02] font-semibold tracking-[-0.025em] text-[var(--app-ink)] xl:text-[5rem]"
            >
              <span
                v-for="(word, index) in posterWords"
                :key="word"
                class="auth-rise block"
                :style="{ animationDelay: `${120 + index * 110}ms` }"
              >
                <em v-if="index === 1" class="font-medium italic">{{ word }}</em>
                <template v-else>{{ word }}</template>
                <span class="text-[var(--app-accent)]" aria-hidden="true">.</span>
              </span>
            </h2>
            <p
              class="auth-rise mx-auto mt-7 max-w-sm text-base leading-relaxed text-[var(--app-ink-soft)]"
              :style="{ animationDelay: '450ms' }"
            >
              {{ t('auth.panel.line') }}
            </p>
          </div>
        </div>
      </aside>

      <!-- Form column (left side) -->
      <div
        class="relative flex w-full flex-col border-[var(--app-line)] bg-[var(--app-surface)] lg:order-1 lg:w-[46%] lg:max-w-xl lg:border-r"
      >
        <div class="flex items-center gap-2.5 px-6 pt-6 md:px-10">
          <span
            class="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--app-line)] bg-[var(--app-bg)]"
          >
            <UIcon name="i-lucide-moon-star" class="h-4 w-4 text-[var(--app-accent)]" />
          </span>
          <span class="app-brand-wordmark" :aria-label="t('app.name')">
            Night<em class="app-brand-wordmark__forge">Forge</em>
          </span>
        </div>

        <div class="flex flex-1 items-center justify-center px-6 py-12 md:px-12">
          <div class="w-full max-w-sm">
            <UIcon
              name="i-lucide-moon-star"
              class="auth-rise block text-2xl text-[var(--app-accent)]"
              :style="{ animationDelay: '0ms' }"
            />
            <h1
              class="auth-rise mt-5 text-4xl font-semibold tracking-[-0.02em] text-[var(--app-ink)]"
              :style="{ animationDelay: '70ms' }"
            >
              {{ t('auth.login.title') }}
            </h1>
            <p
              class="auth-rise mt-2.5 text-sm leading-relaxed text-[var(--app-ink-soft)]"
              :style="{ animationDelay: '140ms' }"
            >
              {{ t('auth.login.subtitle') }}
            </p>

            <form class="mt-10 space-y-5" @submit.prevent="onSubmit">
              <div class="auth-rise" :style="{ animationDelay: '210ms' }">
                <label
                  for="email"
                  class="mb-2 block font-mono text-xs tracking-[0.08em] text-[var(--app-ink-soft)] uppercase"
                >
                  {{ t('auth.fields.email') }}
                </label>
                <input
                  id="email"
                  v-model="email"
                  type="email"
                  autocomplete="email"
                  required
                  :placeholder="t('auth.fields.emailPlaceholder')"
                  class="app-input"
                />
              </div>

              <div class="auth-rise" :style="{ animationDelay: '280ms' }">
                <label
                  for="password"
                  class="mb-2 block font-mono text-xs tracking-[0.08em] text-[var(--app-ink-soft)] uppercase"
                >
                  {{ t('auth.fields.password') }}
                </label>
                <div class="relative w-full">
                  <input
                    id="password"
                    v-model="password"
                    :type="showPassword ? 'text' : 'password'"
                    autocomplete="current-password"
                    required
                    :placeholder="t('auth.fields.passwordPlaceholder')"
                    class="app-input pr-10"
                  />
                  <button
                    type="button"
                    class="absolute top-1/2 right-3 -translate-y-1/2 cursor-pointer text-[var(--app-ink-soft)] transition-colors hover:text-[var(--app-ink)]"
                    :aria-label="showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'"
                    @click="showPassword = !showPassword"
                  >
                    <UIcon :name="showPassword ? 'i-lucide-eye-off' : 'i-lucide-eye'" class="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div class="auth-rise pt-2" :style="{ animationDelay: '350ms' }">
                <button type="submit" :disabled="isLoading" class="app-btn-primary w-full">
                  <UIcon v-if="isLoading" name="i-lucide-loader-circle" class="h-4 w-4 animate-spin" />
                  <span>{{ isLoading ? t('auth.login.submitting') : t('auth.login.submit') }}</span>
                </button>
              </div>

              <p class="auth-rise text-center text-sm text-[var(--app-ink-soft)]" :style="{ animationDelay: '420ms' }">
                {{ t('auth.login.switchQuestion') }}
                <NuxtLink
                  to="/signup"
                  class="font-medium text-[var(--app-ink)] underline underline-offset-4 transition-colors hover:text-[var(--app-accent)]"
                >
                  {{ t('auth.login.switchCta') }}
                </NuxtLink>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'

/**
 * Login page — split-screen "affiche de nuit" auth shell (dark only).
 */
definePageMeta({ layout: false })

const { t } = useI18n()
const { login, isLoading } = useAuth()

const email = ref('')
const password = ref('')
const showPassword = ref(false)

/** Stacked poster words shown on the desktop panel. */
const posterWords = computed<string[]>(() => [t('auth.panel.word1'), t('auth.panel.word2'), t('auth.panel.word3')])

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
