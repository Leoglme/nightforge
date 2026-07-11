<template>
  <div class="app-theme flex h-dvh min-h-0">
    <aside
      class="hidden w-60 shrink-0 border-r border-[var(--app-line)] bg-[var(--app-surface)] p-4 md:flex md:flex-col"
    >
      <div class="mb-6 flex items-center gap-2 px-2">
        <UIcon name="i-lucide-moon-star" class="text-[var(--app-accent)]" />
        <span class="font-semibold">{{ t('app.name') }}</span>
      </div>
      <nav class="flex flex-1 flex-col gap-1">
        <NuxtLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-[var(--app-ink-soft)] hover:bg-[var(--app-surface-2)] hover:text-[var(--app-ink)]"
          active-class="bg-[var(--app-surface-2)] !text-[var(--app-ink)]"
        >
          <UIcon :name="link.icon" />
          {{ link.label }}
        </NuxtLink>
      </nav>
      <UButton color="neutral" variant="outline" icon="i-lucide-log-out" block @click="logout">
        {{ t('nav.logout') }}
      </UButton>
    </aside>

    <div class="flex min-h-0 min-w-0 flex-1 flex-col">
      <header
        class="flex shrink-0 items-center justify-between border-b border-[var(--app-line)] bg-[var(--app-surface)] px-4 py-3"
      >
        <div class="flex items-center gap-2 md:hidden">
          <UIcon name="i-lucide-moon-star" class="text-[var(--app-accent)]" />
          <span class="font-semibold">{{ t('app.name') }}</span>
        </div>
        <div class="ml-auto flex items-center gap-3 text-sm text-[var(--app-ink-soft)]">
          <span class="truncate">{{ userStore.userEmail }}</span>
        </div>
      </header>

      <main class="min-h-0 flex-1" :class="isFullBleed ? 'overflow-hidden' : 'overflow-y-auto p-4 sm:p-6'">
        <slot />
      </main>

      <nav
        class="mobile-tab-bar flex shrink-0 items-stretch justify-around border-t border-[var(--app-line)] bg-[var(--app-surface)] pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] md:hidden"
      >
        <NuxtLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="flex min-h-14 min-w-[4.5rem] flex-1 flex-col items-center justify-center gap-1 px-2 text-[0.7rem] text-[var(--app-ink-soft)]"
          active-class="!text-[var(--app-ink)]"
        >
          <UIcon :name="link.icon" class="text-xl" />
          {{ link.label }}
        </NuxtLink>
      </nav>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'

/**
 * Dashboard layout — sidebar on desktop, bottom tab bar on mobile.
 * The compose route is rendered full-bleed (no padding, no page scroll) so its
 * internal 3-column layout can own the viewport height.
 */
const { t } = useI18n()
const route = useRoute()
const userStore = useUserStore()
const { logout } = useAuth()

const isFullBleed = computed(() => route.path === '/dashboard/compose')

const links = computed(() => [
  { to: '/dashboard', icon: 'i-lucide-layout-dashboard', label: t('nav.dashboard') },
  { to: '/dashboard/compose', icon: 'i-lucide-messages-square', label: t('nav.compose') },
  { to: '/dashboard/queue', icon: 'i-lucide-lightbulb', label: t('nav.queue') },
  { to: '/dashboard/docs', icon: 'i-lucide-book-open', label: t('nav.docs') },
])
</script>
