<template>
  <div class="app-theme flex h-dvh min-h-0">
    <!-- Sidebar (desktop) — hidden on Composer to maximize workspace -->
    <aside
      v-if="!isComposePage"
      class="hidden w-64 shrink-0 flex-col border-r border-[var(--app-line)] bg-[var(--app-surface)] md:flex"
    >
      <!-- Brand -->
      <div class="border-b border-[var(--app-line)] px-4 pt-4 pb-3">
        <div class="flex items-center gap-2.5 px-1">
          <span
            class="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--app-line)] bg-[var(--app-bg)]"
          >
            <UIcon name="i-lucide-moon-star" class="h-4 w-4 text-[var(--app-accent)]" />
          </span>
          <span class="app-brand-wordmark" :aria-label="t('app.name')">
            Night<em class="app-brand-wordmark__forge">Forge</em>
          </span>
        </div>
      </div>

      <!-- Navigation -->
      <nav class="flex flex-1 flex-col gap-1.5 overflow-y-auto px-4 py-4">
        <NuxtLink v-for="link in links" :key="link.to" :to="link.to" :class="navItemClass(isActive(link.to))">
          <span :class="navBarClass(isActive(link.to))"></span>
          <UIcon :name="link.icon" class="h-4 w-4 shrink-0" />
          <span class="truncate">{{ link.label }}</span>
        </NuxtLink>
      </nav>

      <!-- Footer: user block + account menu -->
      <div class="relative border-t border-[var(--app-line)] px-4 py-3">
        <div v-if="showUserMenu" class="fixed inset-0 z-40" @click="showUserMenu = false"></div>

        <div
          v-if="showUserMenu"
          class="app-card absolute inset-x-4 bottom-full z-50 mb-1.5 p-1 shadow-[var(--app-shadow-soft)]"
        >
          <button
            type="button"
            class="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs font-medium text-[var(--app-red)] transition-colors hover:bg-[var(--app-red-soft)]"
            @click="handleLogout"
          >
            <UIcon name="i-lucide-log-out" class="h-3.5 w-3.5" />
            {{ t('nav.logout') }}
          </button>
        </div>

        <button
          class="group flex w-full cursor-pointer items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-[var(--app-surface-2)]"
          :aria-expanded="showUserMenu"
          aria-label="Ouvrir le menu du compte"
          @click.stop="showUserMenu = !showUserMenu"
        >
          <span
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--app-ink)] font-mono text-[0.65rem] font-semibold text-[var(--app-surface)]"
          >
            {{ userInitials }}
          </span>
          <span class="min-w-0 flex-1">
            <span class="block truncate text-sm font-medium text-[var(--app-ink)]">{{ userName }}</span>
            <span class="block truncate text-xs text-[var(--app-ink-soft)]">{{ userEmail }}</span>
          </span>
          <UIcon name="i-lucide-chevrons-up-down" class="h-3.5 w-3.5 shrink-0 text-[var(--app-ink-soft)]" />
        </button>
      </div>
    </aside>

    <div class="flex min-h-0 min-w-0 flex-1 flex-col">
      <main
        class="min-h-0 flex-1"
        :class="isFullBleed ? 'flex flex-col overflow-hidden' : 'overflow-y-auto p-4 sm:p-6'"
      >
        <slot />
      </main>

      <nav
        class="mobile-tab-bar flex shrink-0 items-stretch justify-around border-t border-[var(--app-line)] bg-[var(--app-surface)] pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] md:hidden"
      >
        <NuxtLink
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="relative flex min-h-14 min-w-[4.5rem] flex-1 flex-col items-center justify-center gap-1 px-2 text-[0.7rem] text-[var(--app-ink-soft)]"
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
import { computed, ref } from 'vue'
import { useUserStore } from '~/stores/user'

/**
 * Dashboard layout — grouped sidebar on desktop, bottom tab bar on mobile.
 * No top header (brand lives in the sidebar). Compose is full-bleed and hides the sidebar on desktop.
 */
const { t } = useI18n()
const route = useRoute()
const { logout } = useAuth()
const userStore = useUserStore()

/** Account menu (opens above the user block). */
const showUserMenu = ref(false)

const isComposePage = computed(() => route.path === '/dashboard/compose')
const isRunDetailPage = computed(() => /^\/dashboard\/runs\/\d+/.test(route.path))
const isFullBleed = computed(() => isComposePage.value || isRunDetailPage.value)

/**
 * Flat navigation (no categories). Machines stays out of the menu — it's
 * already reachable from the dashboard overview cards.
 */
const links = computed(() => [
  { to: '/dashboard', icon: 'i-lucide-layout-dashboard', label: t('nav.dashboard') },
  { to: '/dashboard/compose', icon: 'i-lucide-messages-square', label: t('nav.compose') },
  { to: '/dashboard/queue', icon: 'i-lucide-lightbulb', label: t('nav.queue') },
  { to: '/dashboard/runs', icon: 'i-lucide-rocket', label: t('nav.runs') },
])

/** User display name. */
const userName = computed(() => userStore.userName || 'NightForge')

/** User email. */
const userEmail = computed(() => userStore.userEmail || '—')

/** User initials shown in the avatar circle. */
const userInitials = computed(() => {
  const name = userStore.userName
  if (!name) return 'NF'
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2 && parts[0] && parts[1]) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
  }
  return name.substring(0, 2).toUpperCase()
})

/**
 * Whether a route is active (exact, or a sub-route for non-root paths).
 * @param path - Route path to check.
 * @returns True if the route is active.
 */
function isActive(path: string): boolean {
  if (route.path === path) return true
  if (path !== '/dashboard' && route.path.startsWith(path + '/')) return true
  return false
}

/**
 * Classes of a navigation row for a given active state.
 * @param active - Whether the row matches the current route.
 * @returns Tailwind classes for the row.
 */
function navItemClass(active: boolean): string {
  const base =
    'relative flex cursor-pointer items-center gap-2.5 rounded-lg py-2 pr-3 pl-4 text-sm font-medium transition-colors'
  if (active) {
    return `${base} bg-[var(--app-surface-2)] text-[var(--app-ink)]`
  }
  return `${base} text-[var(--app-ink-soft)] hover:bg-[var(--app-surface-2)] hover:text-[var(--app-ink)]`
}

/**
 * Classes of the amber active indicator bar of a navigation row.
 * @param active - Whether the row matches the current route.
 * @returns Tailwind classes for the indicator.
 */
function navBarClass(active: boolean): string {
  const base = 'absolute top-1/2 left-1 h-4 w-0.5 -translate-y-1/2 rounded-full transition-colors'
  return active ? `${base} bg-[var(--app-accent)]` : `${base} bg-transparent`
}

/**
 * Log the user out from the account menu.
 */
function handleLogout(): void {
  showUserMenu.value = false
  logout()
}
</script>
