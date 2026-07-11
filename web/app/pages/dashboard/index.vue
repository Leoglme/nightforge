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
          <UButton color="neutral" variant="outline" icon="i-lucide-lightbulb" to="/dashboard/queue">
            Ajouter une idée
          </UButton>
          <UButton color="primary" icon="i-lucide-messages-square" to="/dashboard/compose"> Composer la nuit </UButton>
        </div>
      </div>
    </UCard>

    <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <NuxtLink
        v-for="stat in stats"
        :key="stat.label"
        :to="stat.to"
        class="group block rounded-[var(--ui-radius,0.5rem)] transition hover:-translate-y-0.5"
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
    </div>

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
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Machine, Project, Run } from '~/types'
import { listMachines } from '~/services/machinesService'
import { listProjects } from '~/services/projectsService'
import { listRuns } from '~/services/runsService'

/**
 * Dashboard overview page with live refresh.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()

const machines = ref<Machine[]>([])
const projects = ref<Project[]>([])
const runs = ref<Run[]>([])
let timer: ReturnType<typeof setInterval> | null = null

const stats = computed(() => [
  {
    label: 'Machines en ligne',
    value: machines.value.filter((m) => m.online).length,
    icon: 'i-lucide-monitor-check',
    to: '/dashboard/machines',
  },
  { label: 'Machines', value: machines.value.length, icon: 'i-lucide-monitor', to: '/dashboard/machines' },
  { label: 'Projets', value: projects.value.length, icon: 'i-lucide-folder-git-2', to: '/dashboard/compose' },
  { label: t('nav.runs'), value: runs.value.length, icon: 'i-lucide-moon', to: '/dashboard/runs' },
])

/**
 * Refresh all overview data.
 * @returns Nothing.
 */
async function refresh(): Promise<void> {
  ;[machines.value, projects.value, runs.value] = await Promise.all([
    listMachines().catch(() => []),
    listProjects().catch(() => []),
    listRuns().catch(() => []),
  ])
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
