<template>
  <div class="rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] p-3">
    <div class="mb-2 flex items-center justify-between gap-2">
      <span class="app-label flex items-center gap-1.5">
        <UIcon name="i-lucide-timer" class="text-[var(--app-accent)]" />
        Timeline des quotas
      </span>
      <UIcon v-if="loading" name="i-lucide-loader-circle" class="animate-spin text-[var(--app-ink-soft)]" />
    </div>

    <p v-if="!plan && !loading" class="text-xs text-[var(--app-ink-soft)]">
      Choisis une machine et un nombre de quotas pour voir la timeline.
    </p>

    <template v-else-if="plan">
      <!-- Per-quota windows -->
      <ol class="flex flex-col gap-1">
        <li v-for="w in plan.windows" :key="w.index" class="flex items-center gap-2 rounded-md px-1.5 py-1 text-sm">
          <span
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--app-accent-soft)] text-[0.65rem] font-semibold text-[var(--app-accent-ink)]"
          >
            {{ w.index }}
          </span>
          <span class="tabular-nums">{{ formatTimeLabelFr(w.starts_at) }}</span>
          <UIcon name="i-lucide-arrow-right" class="h-3.5 w-3.5 shrink-0 text-[var(--app-ink-soft)]" />
          <span class="font-medium tabular-nums">{{ t('common.reset') }} {{ formatTimeLabelFr(w.resets_at) }}</span>
          <span
            :class="[
              'ml-auto shrink-0 rounded px-1.5 py-0.5 text-[0.6rem] font-medium',
              w.estimated
                ? 'bg-[var(--app-surface)] text-[var(--app-ink-soft)]'
                : 'bg-[var(--app-green-soft,var(--app-accent-soft))] text-[var(--app-green,var(--app-accent-ink))]',
            ]"
          >
            {{ w.estimated ? t('common.estimated') : t('common.real') }}
          </span>
        </li>
      </ol>

      <!-- Launch / fresh quota callout -->
      <div
        class="mt-2 flex items-start gap-2 rounded-lg border border-[var(--app-accent)]/40 bg-[var(--app-accent-soft)] px-3 py-2"
      >
        <UIcon name="i-lucide-sparkles" class="mt-0.5 shrink-0 text-[var(--app-accent-ink)]" />
        <div class="min-w-0 text-sm">
          <div class="font-semibold text-[var(--app-accent-ink)]">
            <template v-if="launchLabel"> Démarrage prévu à {{ launchLabel }} </template>
            <template v-else> Quota vierge dispo à {{ formatTimeLabelFr(plan.fresh_quota_available_at) }} </template>
          </div>
          <div class="text-xs text-[var(--app-ink-soft)]">
            {{ launchRelative }}<span v-if="wakeText"> · {{ wakeText }}</span>
          </div>
        </div>
      </div>

      <p v-if="infoMessage" class="mt-2 flex items-start gap-1.5 text-xs text-[var(--app-ink-soft)]">
        <UIcon name="i-lucide-info" class="mt-0.5 shrink-0" />
        <span>{{ infoMessage }}</span>
      </p>

      <UAlert
        v-if="plan.weekly_warning"
        class="mt-2"
        color="warning"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        :description="plan.weekly_warning"
      />
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { QuotaPlan } from '~/types'
import { parseApiDateTime } from '~/utils/datetime'

/**
 * Quota timeline — a readable breakdown of each 5-hour window's reset time and when a fresh
 * quota becomes available, shown live while configuring a night.
 */
const props = defineProps<{
  plan: QuotaPlan | null
  loading: boolean
}>()

const { t } = useI18n()

/**
 * Whether the first window is a pure estimate (no real reset anchor available).
 */
const firstEstimated = computed(() => props.plan?.windows[0]?.estimated ?? false)

/**
 * ISO timestamp when the run actually starts (after waiting for reset), if any.
 */
const launchAt = computed(() => props.plan?.wait_until ?? null)

/**
 * Human label for the planned launch instant.
 */
const launchLabel = computed(() => {
  if (!launchAt.value) {
    return ''
  }
  const diffMs = parseApiDateTime(launchAt.value).getTime() - Date.now()
  if (diffMs <= 60_000) {
    return ''
  }
  return formatTimeLabelFr(launchAt.value)
})

/**
 * Contextual helper text under the timeline.
 */
const infoMessage = computed(() => {
  if (!props.plan || !firstEstimated.value) {
    if (props.plan?.anchor_source === 'live') {
      return 'Créneau calé sur le bucket Claude lu en direct via l’agent.'
    }
    if (props.plan?.anchor_source === 'snapshot') {
      return 'Créneau basé sur le dernier relevé quota de la machine (agent peut-être hors ligne).'
    }
    return ''
  }
  return 'Estimation depuis maintenant. Choisis une machine en ligne pour lire le reset Claude réel (OAuth via l’agent).'
})

/**
 * Human-friendly relative delay until launch or fresh quota.
 */
const launchRelative = computed(() => {
  if (!props.plan) {
    return ''
  }
  const target = launchAt.value ?? props.plan.fresh_quota_available_at
  const diffMs = parseApiDateTime(target).getTime() - Date.now()
  if (diffMs <= 0) {
    return launchAt.value ? 'démarrage imminent' : 'disponible maintenant'
  }
  const totalMin = Math.round(diffMs / 60000)
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  if (h === 0) {
    return `dans ~${m} min`
  }
  return m === 0 ? `dans ~${h} h` : `dans ~${h} h ${m} min`
})

/**
 * Description of the fresh quota relative to the wake time, if provided.
 */
const wakeText = computed(() => {
  const delta = props.plan?.hours_after_wake
  if (delta === null || delta === undefined) {
    return ''
  }
  if (delta > 0.05) {
    return `≈ ${formatHours(delta)} après ton réveil`
  }
  if (delta < -0.05) {
    return `prêt ${formatHours(Math.abs(delta))} avant ton réveil`
  }
  return 'prêt à ton réveil'
})

/**
 * Format a decimal hour count as "Xh" or "Xh Ymin".
 * @param hours - Decimal hours.
 * @returns A short human string.
 */
function formatHours(hours: number): string {
  const h = Math.floor(hours)
  const m = Math.round((hours - h) * 60)
  if (h === 0) {
    return `${m} min`
  }
  return m === 0 ? `${h} h` : `${h} h ${m} min`
}
</script>
