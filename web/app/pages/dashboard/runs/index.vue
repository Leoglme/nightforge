<template>
  <div class="flex flex-col gap-6">
    <h1 class="app-page-title">{{ t('nav.runs') }}</h1>

    <UCard>
      <div v-if="runs.length === 0" class="py-6 text-center text-sm text-[var(--app-ink-soft)]">
        Aucun lancement pour l’instant. Lance un prompt depuis la
        <NuxtLink to="/dashboard/queue" class="underline">file d’attente</NuxtLink>
        ou compose une nuit dans le
        <NuxtLink to="/dashboard/compose" class="underline">compositeur</NuxtLink>.
      </div>
      <ul v-else class="divide-y divide-[var(--app-line)]">
        <li v-for="run in runs" :key="run.id" class="flex items-center justify-between gap-3 py-3 text-sm">
          <NuxtLink :to="`/dashboard/runs/${run.id}`" class="min-w-0 flex-1 hover:opacity-80">
            <div class="font-medium">
              {{ run.kind === 'quick' ? t('common.launch') : t('common.night') }} #{{ run.id }}
            </div>
            <div class="text-xs text-[var(--app-ink-soft)]">
              <template v-if="run.kind === 'quick'">
                {{ t('common.machine') }} {{ machineLabel(run.machine_id) }}
                <template v-if="run.started_at"> · {{ formatDateTimeFr(run.started_at) }}</template>
              </template>
              <template v-else>
                {{ t('common.machine') }} {{ machineLabel(run.machine_id) }} · {{ run.quota_count }} quota(s) ·
                {{ run.parallel ? t('common.parallel').toLowerCase() : t('common.sequential').toLowerCase() }}
              </template>
            </div>
          </NuxtLink>
          <div class="flex items-center gap-2">
            <StatusBadge :status="run.status" dot />
            <UButton
              v-if="['SCHEDULED', 'RUNNING', 'WAITING_QUOTA'].includes(run.status)"
              size="xs"
              color="error"
              variant="outline"
              @click="stop(run.id)"
            >
              {{ t('common.stop') }}
            </UButton>
            <UButton
              size="xs"
              color="neutral"
              variant="ghost"
              icon="i-lucide-chevron-right"
              :to="`/dashboard/runs/${run.id}`"
            />
          </div>
        </li>
      </ul>
    </UCard>
  </div>
</template>

<script lang="ts" setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { Machine, Run } from '~/types'
import { formatDateTimeFr } from '~/utils/datetime'
import { listMachines } from '~/services/machinesService'
import { listRuns, stopRun } from '~/services/runsService'

/**
 * Runs list — nights and quick launches.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const runs = ref<Run[]>([])
const machines = ref<Machine[]>([])
let timer: ReturnType<typeof setInterval> | null = null

function machineLabel(machineId: number): string {
  return machines.value.find((m) => m.id === machineId)?.name ?? `#${machineId}`
}

async function refresh(): Promise<void> {
  runs.value = await listRuns().catch(() => [])
}

async function stop(id: number): Promise<void> {
  await stopRun(id)
  await refresh()
}

onMounted(async () => {
  machines.value = await listMachines().catch(() => [])
  refresh()
  timer = setInterval(refresh, 12000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
