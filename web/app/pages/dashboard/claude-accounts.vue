<template>
  <div class="flex flex-col gap-6">
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="mb-1">
          <NuxtLink
            to="/dashboard"
            class="inline-flex items-center gap-1 text-xs text-[var(--app-ink-soft)] transition hover:text-[var(--app-ink)]"
          >
            <UIcon name="i-lucide-arrow-left" class="h-3.5 w-3.5" />
            Tableau de bord
          </NuxtLink>
        </div>
        <h1 class="app-page-title">Comptes Claude</h1>
        <p class="text-sm text-[var(--app-ink-soft)]">Quotas par compte et date de reset.</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <UButton color="neutral" variant="outline" icon="i-lucide-refresh-cw" :loading="refreshing" @click="refresh">
          Actualiser
        </UButton>
        <UButton
          v-if="showImportMachine && !machineLoginId"
          color="neutral"
          variant="outline"
          icon="i-lucide-hard-drive-download"
          :loading="importing"
          @click="importMachine"
        >
          Importer machine
        </UButton>
        <UButton v-if="machineLoginId" color="neutral" variant="ghost" size="sm" @click="cancelMachineLogin">
          Annuler connexion
        </UButton>
        <UButton color="primary" icon="i-lucide-plus" @click="openCreate">Ajouter</UButton>
      </div>
    </div>

    <p
      v-if="bannerError"
      class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-200"
    >
      {{ bannerError }}
    </p>

    <div
      v-if="machineLoginId"
      class="flex flex-col gap-2 rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] px-4 py-3"
    >
      <div class="flex items-center gap-2 text-sm font-medium text-[var(--app-ink)]">
        <UIcon name="i-lucide-loader-circle" class="h-4 w-4 animate-spin text-[var(--app-ink-soft)]" />
        <span>Connexion Claude en cours…</span>
      </div>
      <p v-if="machineLoginNote" class="text-xs text-[var(--app-ink-soft)]">{{ machineLoginNote }}</p>
      <a
        v-if="machineLoginUrl"
        :href="machineLoginUrl"
        target="_blank"
        rel="noopener noreferrer"
        class="text-xs text-[var(--app-accent)] underline-offset-2 hover:underline"
      >
        Ouvrir la fenêtre de connexion manuellement
      </a>
    </div>

    <div v-if="loading && !overview" class="flex justify-center py-16">
      <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
    </div>

    <template v-else>
      <!-- Pinned machine session -->
      <UCard v-if="overview?.machine" class="ring-1 ring-[#D97757]/25">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div class="flex min-w-0 items-start gap-3">
            <div
              class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#D97757]/15 ring-1 ring-[var(--app-line)]"
            >
              <ClaudeLogo class="h-6 w-6 text-[#D97757]" />
            </div>
            <div class="min-w-0">
              <div class="mb-1 flex flex-wrap items-center gap-2">
                <UBadge color="primary" variant="subtle" size="sm">Épinglé</UBadge>
                <UBadge v-if="overview.machine_preferred" color="success" variant="subtle" size="sm">
                  Prioritaire
                </UBadge>
                <span class="font-medium text-[var(--app-ink)]">{{ overview.machine.label }}</span>
              </div>
              <p v-if="overview.machine.error" class="text-sm text-amber-600 dark:text-amber-300">
                {{ overview.machine.error }}
              </p>
            </div>
          </div>
          <div class="text-right">
            <div class="text-2xl font-semibold text-[var(--app-ink)] tabular-nums">
              {{
                pctLabel(avgUtilization(overview.machine.five_hour_utilization, overview.machine.seven_day_utilization))
              }}
            </div>
            <p class="text-[11px] text-[var(--app-ink-soft)]">moyenne 5h + 7j</p>
          </div>
        </div>
        <div
          class="mt-4 grid gap-3"
          :class="overview.machine.seven_day_opus_utilization != null ? 'sm:grid-cols-3' : 'sm:grid-cols-2'"
        >
          <ClaudeUsageBar label="Fenêtre 5 h" :utilization="overview.machine.five_hour_utilization" />
          <ClaudeUsageBar label="Hebdomadaire" :utilization="overview.machine.seven_day_utilization" />
          <ClaudeUsageBar
            v-if="overview.machine.seven_day_opus_utilization != null"
            label="Hebdomadaire Fable"
            :utilization="overview.machine.seven_day_opus_utilization"
          />
        </div>
        <p v-if="resetLabel(overview.machine.resets_at)" class="mt-3 text-[11px] text-[var(--app-ink-soft)]">
          Reset {{ resetLabel(overview.machine.resets_at) }}
        </p>
      </UCard>

      <!-- Vault accounts -->
      <div class="flex flex-col gap-3">
        <div class="flex items-center justify-between gap-2">
          <h2 class="app-label">Comptes enregistrés</h2>
          <span v-if="overview?.selected_account_id" class="text-[11px] text-[var(--app-ink-soft)]">
            Prochain prompt → #{{ overview.selected_account_id }}
          </span>
        </div>

        <div
          v-if="!overview?.accounts.length"
          class="rounded-lg border border-dashed border-[var(--app-line)] px-4 py-10 text-center text-sm text-[var(--app-ink-soft)]"
        >
          Aucun autre compte. Ajoute un compte Claude supplémentaire pour le switch auto.
        </div>

        <div v-for="account in overview?.accounts || []" :key="account.id">
          <UCard class="h-full" :class="account.id === overview?.selected_account_id ? 'ring-1 ring-[#D97757]/30' : ''">
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div class="flex min-w-0 items-start gap-3">
                <div
                  class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#D97757]/15 ring-1 ring-[var(--app-line)]"
                >
                  <ClaudeLogo class="h-6 w-6 text-[#D97757]" />
                </div>
                <div class="min-w-0">
                  <div class="mb-1 flex flex-wrap items-center gap-2">
                    <span class="font-medium text-[var(--app-ink)]">{{ account.label }}</span>
                    <UBadge
                      v-if="account.id === overview?.selected_account_id"
                      color="success"
                      variant="subtle"
                      size="sm"
                    >
                      Prioritaire
                    </UBadge>
                    <UBadge v-if="isFull(account)" color="error" variant="subtle" size="sm">100 %</UBadge>
                    <UBadge v-else-if="hasRoom(account)" color="success" variant="subtle" size="sm">Dispo</UBadge>
                    <UBadge v-if="!account.is_active" color="neutral" variant="subtle" size="sm">Inactif</UBadge>
                  </div>
                  <p v-if="account.last_error" class="mt-1 text-xs text-amber-600 dark:text-amber-300">
                    {{ account.last_error }}
                  </p>
                </div>
              </div>
              <div class="flex items-start gap-3">
                <div class="text-right">
                  <div class="text-2xl font-semibold tabular-nums" :class="utilClass(accountAverage(account))">
                    {{ pctLabel(accountAverage(account)) }}
                  </div>
                  <p class="text-[11px] text-[var(--app-ink-soft)]">moyenne</p>
                </div>
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="sm"
                  icon="i-lucide-pencil"
                  title="Modifier"
                  @click="openEdit(account)"
                />
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="sm"
                  icon="i-lucide-trash-2"
                  title="Supprimer"
                  @click="removeAccount(account)"
                />
              </div>
            </div>
            <div
              class="mt-4 grid gap-3"
              :class="account.seven_day_opus_utilization != null ? 'sm:grid-cols-3' : 'sm:grid-cols-2'"
            >
              <ClaudeUsageBar label="Fenêtre 5 h" :utilization="account.five_hour_utilization" />
              <ClaudeUsageBar label="Hebdomadaire" :utilization="account.seven_day_utilization" />
              <ClaudeUsageBar
                v-if="account.seven_day_opus_utilization != null"
                label="Hebdomadaire Fable"
                :utilization="account.seven_day_opus_utilization"
              />
            </div>
            <div class="mt-3 text-[11px] text-[var(--app-ink-soft)]">
              <span v-if="resetLabel(account.resets_at)">Reset {{ resetLabel(account.resets_at) }}</span>
              <span v-else>Date de reset inconnue</span>
            </div>
          </UCard>
        </div>
      </div>
    </template>

    <ClaudeAccountFormDrawer
      :open="formOpen"
      :mode="formMode"
      :account="selectedAccount"
      @close="formOpen = false"
      @saved="onSaved"
    />
  </div>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { ClaudeAccount, ClaudeAccountsOverview } from '~/types'
import {
  cancelClaudeLogin,
  deleteClaudeAccount,
  importMachineClaudeSession,
  listClaudeAccounts,
  pollClaudeLogin,
  refreshClaudeAccounts,
  startClaudeLogin,
} from '~/services/claudeAccountsService'
import { formatDateTimeFr, parseApiDateTime } from '~/utils/datetime'

definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const overview = ref<ClaudeAccountsOverview | null>(null)
const loading = ref(false)
const refreshing = ref(false)
const importing = ref(false)
const bannerError = ref<string | null>(null)

const machineLoginId = ref<string | null>(null)
const machineLoginUrl = ref<string | null>(null)
const machineLoginNote = ref<string | null>(null)
let machinePollTimer: ReturnType<typeof setInterval> | null = null

/**
 * Hide import once the live machine session is vaulted (API auto-syncs it).
 */
const showImportMachine = computed(() => {
  const data = overview.value
  if (!data) return false
  if (data.machine_imported) return false
  const machineEmail = data.machine?.email?.trim().toLowerCase()
  if (machineEmail) {
    const inVault = data.accounts.some((account) => (account.email || '').trim().toLowerCase() === machineEmail)
    if (inVault) return false
  }
  if (data.machine?.source === 'live' && machineEmail) return false
  return true
})

const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const selectedAccount = ref<ClaudeAccount | null>(null)

const toast = useToast()

/**
 * Compact percent label.
 */
function pctLabel(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)} %`
}

/**
 * Average of the buckets used to rank accounts (5h + 7j).
 */
function avgUtilization(fiveHour?: number | null, sevenDay?: number | null): number | null {
  const values = [fiveHour, sevenDay].filter((v): v is number => v != null)
  if (!values.length) return null
  return values.reduce((a, b) => a + b, 0) / values.length
}

function accountAverage(account: ClaudeAccount): number | null {
  return avgUtilization(account.five_hour_utilization, account.seven_day_utilization)
}

/**
 * Color the average number.
 */
function utilClass(value?: number | null): string {
  if (value == null) return 'text-[var(--app-ink)]'
  if (value >= 0.999) return 'text-red-500'
  if (value >= 0.85) return 'text-amber-500'
  return 'text-[var(--app-ink)]'
}

/**
 * Whether both known buckets are exhausted.
 */
function isFull(account: ClaudeAccount): boolean {
  const avg = accountAverage(account)
  return avg != null && avg >= 0.999
}

/**
 * Whether the account still has headroom.
 */
function hasRoom(account: ClaudeAccount): boolean {
  const avg = accountAverage(account)
  return avg != null && avg < 0.999
}

/**
 * Format reset timestamp.
 */
function resetLabel(value?: string | null): string | null {
  if (!value) return null
  const d = parseApiDateTime(value)
  if (Number.isNaN(d.getTime()) || d.getFullYear() < 2020) return null
  return formatDateTimeFr(d)
}

/**
 * Initial load.
 */
async function load(): Promise<void> {
  loading.value = true
  bannerError.value = null
  try {
    overview.value = await listClaudeAccounts()
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : 'Chargement impossible'
  } finally {
    loading.value = false
  }
}

/**
 * Force-refresh all quotas.
 */
async function refresh(): Promise<void> {
  refreshing.value = true
  bannerError.value = null
  try {
    overview.value = await refreshClaudeAccounts()
    toast.add({ title: 'Quotas actualisés', color: 'success' })
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : 'Actualisation impossible'
  } finally {
    refreshing.value = false
  }
}

function stopMachinePolling(): void {
  if (machinePollTimer) {
    clearInterval(machinePollTimer)
    machinePollTimer = null
  }
}

function clearMachineLoginUi(): void {
  stopMachinePolling()
  machineLoginId.value = null
  machineLoginUrl.value = null
  machineLoginNote.value = null
}

/**
 * True when the import failed because no local Claude session exists yet.
 * Does NOT match agent timeout / offline errors (those must not open the browser).
 */
function isMissingLocalSessionError(message: string): boolean {
  if (/timeout|hors ligne|offline|aucune machine|n’a pas répondu|n'a pas répondu/i.test(message)) {
    return false
  }
  return /session claude local|introuvable|non d[eé]tect|reconnecte-toi via le navigateur/i.test(message)
}

/**
 * After a successful login, vault the (now present) machine session.
 */
async function finishMachineImport(): Promise<void> {
  await importMachineClaudeSession()
  overview.value = await listClaudeAccounts()
  if (overview.value) {
    overview.value.machine_imported = true
  }
  clearMachineLoginUi()
  toast.add({ title: 'Session machine importée', color: 'success' })
}

/**
 * Open ``claude auth login`` so the user can connect this machine, then import.
 */
async function startMachineLoginFlow(): Promise<void> {
  bannerError.value = null
  const started = await startClaudeLogin({ keepOnMachine: true })
  machineLoginId.value = started.login_id
  machineLoginUrl.value = started.login_url || null
  machineLoginNote.value = started.note || null
  stopMachinePolling()
  machinePollTimer = setInterval(() => {
    void pollMachineLogin()
  }, 2000)
}

async function pollMachineLogin(): Promise<void> {
  if (!machineLoginId.value) return
  try {
    const result = await pollClaudeLogin(machineLoginId.value)
    if (result.status === 'ready' && result.oauth) {
      stopMachinePolling()
      importing.value = true
      try {
        await finishMachineImport()
      } catch (err) {
        bannerError.value = err instanceof Error ? err.message : 'Import impossible après connexion'
        clearMachineLoginUi()
      } finally {
        importing.value = false
      }
    } else if (result.status === 'error' && result.error) {
      bannerError.value = result.error
      clearMachineLoginUi()
    } else if (result.login_url) {
      machineLoginUrl.value = result.login_url
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : ''
    if (/timeout|hors ligne|offline|aucune machine/i.test(message)) {
      bannerError.value = message
      clearMachineLoginUi()
    }
  }
}

async function cancelMachineLogin(): Promise<void> {
  const id = machineLoginId.value
  clearMachineLoginUi()
  if (id) {
    try {
      await cancelClaudeLogin(id)
    } catch {
      // ignore
    }
  }
}

/**
 * Import local agent session into the vault.
 * If Claude is not logged in on this machine, open the login window instead.
 */
async function importMachine(): Promise<void> {
  if (importing.value || machineLoginId.value) return
  importing.value = true
  bannerError.value = null
  try {
    await finishMachineImport()
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Import impossible'
    if (isMissingLocalSessionError(message)) {
      try {
        await startMachineLoginFlow()
        toast.add({
          title: 'Connecte-toi à Claude',
          description: 'Aucune session locale — une fenêtre de connexion a été ouverte.',
          color: 'primary',
        })
      } catch (loginErr) {
        bannerError.value = loginErr instanceof Error ? loginErr.message : 'Impossible d’ouvrir la connexion Claude'
      }
    } else {
      bannerError.value = message
    }
  } finally {
    importing.value = false
  }
}

function openCreate(): void {
  formMode.value = 'create'
  selectedAccount.value = null
  formOpen.value = true
}

function openEdit(account: ClaudeAccount): void {
  selectedAccount.value = account
  formMode.value = 'edit'
  formOpen.value = true
}

async function onSaved(): Promise<void> {
  overview.value = await listClaudeAccounts()
}

async function removeAccount(account: ClaudeAccount): Promise<void> {
  if (!confirm(`Supprimer le compte « ${account.label} » ?`)) return
  try {
    await deleteClaudeAccount(account.id)
    overview.value = await listClaudeAccounts()
    toast.add({ title: 'Compte supprimé', color: 'neutral' })
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : 'Suppression impossible'
  }
}

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  stopMachinePolling()
})
</script>
