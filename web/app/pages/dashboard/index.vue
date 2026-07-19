<template>
  <div class="flex flex-col gap-6">
    <div>
      <h1 class="app-page-title">{{ t('nav.dashboard') }}</h1>
      <p class="text-sm text-[var(--app-ink-soft)]">Vue d'ensemble de tes machines, projets et nuits.</p>
    </div>

    <UCard>
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="font-medium">Prêt pour la nuit ?</div>
          <p class="text-sm text-[var(--app-ink-soft)]">
            Compose tes messages projet par projet, puis lance l'exécution automatique.
          </p>
        </div>
        <div class="flex flex-col gap-2 sm:flex-row">
          <UButton color="neutral" variant="outline" icon="i-lucide-list-todo" to="/dashboard/queue">
            File d'attente
          </UButton>
          <UButton color="primary" icon="i-lucide-messages-square" to="/dashboard/compose"> Composer la nuit </UButton>
        </div>
      </div>
    </UCard>

    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <template v-for="stat in stats" :key="stat.label">
        <NuxtLink
          v-if="stat.to"
          :to="stat.to"
          class="group block cursor-pointer rounded-[var(--ui-radius,0.5rem)] text-left transition hover:-translate-y-0.5"
        >
          <UCard class="h-full transition group-hover:ring-2 group-hover:ring-[var(--app-accent)]/40">
            <div class="flex items-start justify-between gap-2">
              <div class="app-label">{{ stat.label }}</div>
              <UIcon
                :name="stat.icon"
                class="text-[var(--app-ink-soft)] transition group-hover:text-[var(--app-accent)]"
              />
            </div>
            <div class="mt-1 text-2xl font-semibold">{{ stat.value }}</div>
          </UCard>
        </NuxtLink>
        <button
          v-else
          type="button"
          class="group block w-full cursor-pointer rounded-[var(--ui-radius,0.5rem)] text-left transition hover:-translate-y-0.5"
          @click="stat.onClick?.()"
        >
          <UCard class="h-full transition group-hover:ring-2 group-hover:ring-[var(--app-accent)]/40">
            <div class="flex items-start justify-between gap-2">
              <div class="app-label">{{ stat.label }}</div>
              <UIcon
                :name="stat.icon"
                class="text-[var(--app-ink-soft)] transition group-hover:text-[var(--app-accent)]"
              />
            </div>
            <div class="mt-1 text-2xl font-semibold">{{ stat.value }}</div>
          </UCard>
        </button>
      </template>
    </div>

    <UCard>
      <template #header>
        <div class="flex items-center justify-between gap-2">
          <span class="app-label">Utilisation</span>
          <UButton
            color="neutral"
            variant="ghost"
            size="xs"
            icon="i-lucide-refresh-cw"
            :loading="usageStore.loading"
            title="Actualiser les quotas"
            aria-label="Actualiser les quotas"
            @click="usageStore.refresh()"
          />
        </div>
      </template>

      <div v-if="usageStore.loading && !usage" class="flex justify-center py-8">
        <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
      </div>

      <div v-else-if="!hasAnyUsage" class="py-6 text-center text-sm text-[var(--app-ink-soft)]">
        Pas encore de lecture quota — ouvre l’app desktop, puis appuie sur actualiser
        <template v-if="usage?.quota_auth_error || usageStore.error">
          <br />
          <span class="text-amber-600">{{ usage?.quota_auth_error || usageStore.error }}</span>
        </template>
        <div class="mt-4 flex flex-wrap justify-center gap-2">
          <UButton
            color="neutral"
            variant="outline"
            size="sm"
            icon="i-lucide-layout-list"
            to="/dashboard/claude-accounts"
          >
            Tous les comptes Claude
          </UButton>
          <UButton
            color="neutral"
            variant="outline"
            size="sm"
            icon="i-lucide-layout-list"
            to="/dashboard/cursor-accounts"
          >
            Tous les comptes Cursor
          </UButton>
        </div>
      </div>

      <div v-else class="flex flex-col gap-5">
        <div v-if="claudeBuckets.length">
          <div class="mb-3 flex items-start justify-between gap-3">
            <div class="flex min-w-0 items-center gap-3">
              <ClaudeLogo class="h-5 w-5 shrink-0 text-[#D97757]" />
              <div class="text-sm font-medium text-[var(--app-ink)]">Claude Max</div>
            </div>
            <UButton
              color="primary"
              size="xs"
              icon="i-lucide-layout-list"
              to="/dashboard/claude-accounts"
              title="Voir tous les comptes Claude et leurs quotas"
            >
              Tous les comptes
            </UButton>
          </div>
          <ul class="flex flex-col gap-4">
            <UsageQuotaRow
              v-for="bucket in claudeBuckets"
              :key="bucket.bucket"
              :label="bucket.label"
              :utilization="bucket.utilization"
            />
          </ul>
          <div v-if="claudeResetLabel" class="mt-2.5">
            <span class="app-badge app-badge--info w-fit gap-1 px-2 py-0.5 text-[11px] tabular-nums">
              <UIcon name="i-lucide-clock-3" class="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
              Reset {{ claudeResetLabel }}
            </span>
          </div>
        </div>

        <div v-if="cursorBuckets.length" class="border-t border-[var(--app-line)] pt-4">
          <div class="mb-3 flex items-start justify-between gap-3">
            <div class="flex min-w-0 items-center gap-3">
              <CursorLogo class="h-5 w-5 shrink-0 text-[var(--app-ink)]" />
              <div class="text-sm font-medium text-[var(--app-ink)]">Cursor</div>
            </div>
            <UButton
              color="primary"
              size="xs"
              icon="i-lucide-layout-list"
              to="/dashboard/cursor-accounts"
              title="Voir tous les comptes Cursor et leurs quotas"
            >
              Tous les comptes
            </UButton>
          </div>
          <ul class="flex flex-col gap-4">
            <UsageQuotaRow
              v-for="bucket in cursorBuckets"
              :key="bucket.bucket"
              :label="bucket.label"
              :utilization="bucket.utilization"
            />
          </ul>
          <div v-if="cursorResetLabel" class="mt-2.5">
            <span class="app-badge app-badge--info w-fit gap-1 px-2 py-0.5 text-[11px] tabular-nums">
              <UIcon name="i-lucide-clock-3" class="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
              Reset {{ cursorResetLabel }}
            </span>
          </div>
        </div>

        <div v-else class="flex items-center justify-between gap-2 border-t border-[var(--app-line)] pt-4">
          <p class="text-sm text-[var(--app-ink-soft)]">Gère plusieurs comptes Cursor et leurs quotas.</p>
          <UButton color="primary" size="xs" icon="i-lucide-layout-list" to="/dashboard/cursor-accounts">
            Tous les comptes
          </UButton>
        </div>
      </div>
    </UCard>

    <UCard>
      <template #header>
        <span class="app-label">Nuits récentes</span>
      </template>
      <div v-if="runs.length === 0" class="py-6 text-center text-sm text-[var(--app-ink-soft)]">
        Aucune nuit pour le moment.
      </div>
      <ul v-else class="divide-y divide-[var(--app-line)]">
        <li v-for="run in runs" :key="run.id" class="flex items-center justify-between py-3 text-sm">
          <NuxtLink :to="`/dashboard/runs/${run.id}`" class="hover:opacity-80">
            {{ t('common.night') }} #{{ run.id }} — {{ t('common.machine').toLowerCase() }} {{ run.machine_id }}
          </NuxtLink>
          <StatusBadge :status="run.status" dot />
        </li>
      </ul>
    </UCard>
  </div>

  <ProjectsManageDrawer :open="projectsOpen" @close="projectsOpen = false" @changed="refreshStats" />
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import UsageQuotaRow from '~/components/UsageQuotaRow.vue'
import type { Machine, Project, Run, UsageBucket } from '~/types'
import { formatDateTimeFr, parseApiDateTime } from '~/utils/datetime'
import { listMachines } from '~/services/machinesService'
import { listProjects } from '~/services/projectsService'
import { listRuns } from '~/services/runsService'
import { useUsageStore } from '~/stores/usage'

/**
 * Dashboard overview — stats poll lightly; usage refreshes only on demand.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const usageStore = useUsageStore()

const machines = ref<Machine[]>([])
const projects = ref<Project[]>([])
const runs = ref<Run[]>([])
const projectsOpen = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const usage = computed(() => usageStore.usage)

const claudeBuckets = computed(() => usage.value?.claude ?? [])

const cursorBuckets = computed((): UsageBucket[] =>
  (usage.value?.cursor ?? []).filter((b) => b.bucket === 'cursor_auto' || b.bucket === 'cursor_api'),
)

const hasAnyUsage = computed(() => Boolean(claudeBuckets.value.length || cursorBuckets.value.length))

const claudeResetLabel = computed(() => resetLabelForBuckets(claudeBuckets.value))

const cursorResetLabel = computed(() => resetLabelForBuckets(cursorBuckets.value))

/**
 * First usable reset timestamp across buckets (one badge per provider section).
 */
function resetLabelForBuckets(buckets: UsageBucket[]): string | null {
  for (const bucket of buckets) {
    if (!bucket.resets_at) continue
    const d = parseApiDateTime(bucket.resets_at)
    if (Number.isNaN(d.getTime()) || d.getFullYear() < 2020) continue
    return formatDateTimeFr(d)
  }
  return null
}

const stats = computed(() => [
  {
    label: 'Machines en ligne',
    value: machines.value.filter((m) => m.online).length,
    icon: 'i-lucide-monitor-check',
    to: '/dashboard/machines',
  },
  { label: 'Machines', value: machines.value.length, icon: 'i-lucide-monitor', to: '/dashboard/machines' },
  {
    label: 'Projets',
    value: projects.value.length,
    icon: 'i-lucide-folder-git-2',
    onClick: () => {
      projectsOpen.value = true
    },
  },
  { label: t('nav.runs'), value: runs.value.length, icon: 'i-lucide-rocket', to: '/dashboard/runs' },
])

/**
 * Refresh overview stats (not usage).
 */
async function refreshStats(): Promise<void> {
  ;[machines.value, projects.value, runs.value] = await Promise.all([
    listMachines().catch(() => []),
    listProjects().catch(() => []),
    listRuns().catch(() => []),
  ])
}

onMounted(() => {
  refreshStats()
  usageStore.ensureLoaded()
  timer = setInterval(refreshStats, 12000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
