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
        <h1 class="app-page-title">Comptes Cursor</h1>
        <p class="text-sm text-[var(--app-ink-soft)]">
          Quotas par compte, date de reset, et rappel email / mot de passe chiffré.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <UButton color="neutral" variant="outline" icon="i-lucide-refresh-cw" :loading="refreshing" @click="refresh">
          Actualiser
        </UButton>
        <UButton
          v-if="showImportMachine"
          color="neutral"
          variant="outline"
          icon="i-lucide-hard-drive-download"
          :loading="importing"
          @click="importMachine"
        >
          Importer machine
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

    <div v-if="loading && !overview" class="flex justify-center py-16">
      <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
    </div>

    <template v-else>
      <!-- Pinned machine session -->
      <UCard v-if="overview?.machine" class="ring-1 ring-[var(--app-accent)]/25">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div class="flex min-w-0 items-start gap-3">
            <UAvatar
              :src="gravatarUrl(overview.machine.email)"
              :alt="overview.machine.email || 'Cursor'"
              :text="avatarInitials(overview.machine.email)"
              size="lg"
              class="ring-1 ring-[var(--app-line)]"
            />
            <div class="min-w-0">
              <div class="mb-1 flex flex-wrap items-center gap-2">
                <UBadge color="primary" variant="subtle" size="sm">Épinglé</UBadge>
                <UBadge v-if="overview.machine_preferred" color="success" variant="subtle" size="sm">
                  Prioritaire
                </UBadge>
                <span class="font-medium text-[var(--app-ink)]">{{ overview.machine.label }}</span>
              </div>
              <p v-if="overview.machine.email" class="truncate text-sm text-[var(--app-ink-soft)]">
                {{ overview.machine.email }}
              </p>
              <p v-else-if="overview.machine.error" class="text-sm text-amber-600 dark:text-amber-300">
                {{ overview.machine.error }}
              </p>
              <p v-else class="text-sm text-[var(--app-ink-soft)]">Email Cursor non détecté</p>
            </div>
          </div>
          <div class="text-right">
            <div class="text-2xl font-semibold text-[var(--app-ink)] tabular-nums">
              {{ pctLabel(overview.machine.average_utilization) }}
            </div>
            <p class="text-[11px] text-[var(--app-ink-soft)]">moyenne Auto + API</p>
          </div>
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <CursorUsageBar label="Composer / Auto" :utilization="overview.machine.auto_utilization" />
          <CursorUsageBar label="API" :utilization="overview.machine.api_utilization" />
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
          Aucun autre compte. Ajoute un compte Cursor supplémentaire pour le switch auto.
        </div>

        <button
          v-for="account in overview?.accounts || []"
          :key="account.id"
          type="button"
          class="group w-full cursor-pointer rounded-[var(--ui-radius,0.5rem)] text-left transition hover:-translate-y-0.5"
          @click="openCredentials(account)"
        >
          <UCard
            class="h-full transition group-hover:ring-2 group-hover:ring-[var(--app-accent)]/40"
            :class="account.id === overview?.selected_account_id ? 'ring-1 ring-[var(--app-accent)]/30' : ''"
          >
            <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0">
                <div class="mb-1 flex flex-wrap items-center gap-2">
                  <span class="font-medium text-[var(--app-ink)]">{{ account.email || 'Email non renseigné' }}</span>
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
              <div class="flex items-start gap-3">
                <div class="text-right">
                  <div class="text-2xl font-semibold tabular-nums" :class="utilClass(account.average_utilization)">
                    {{ pctLabel(account.average_utilization) }}
                  </div>
                  <p class="text-[11px] text-[var(--app-ink-soft)]">moyenne</p>
                </div>
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="sm"
                  icon="i-lucide-trash-2"
                  title="Supprimer"
                  @click.stop="removeAccount(account)"
                />
              </div>
            </div>
            <div class="mt-4 grid gap-3 sm:grid-cols-2">
              <CursorUsageBar label="Composer / Auto" :utilization="account.auto_utilization" />
              <CursorUsageBar label="API" :utilization="account.api_utilization" />
            </div>
            <div class="mt-4 flex flex-col gap-2.5">
              <p class="text-[11px] text-[var(--app-ink-soft)]">
                <span v-if="resetLabel(account.resets_at)">Reset {{ resetLabel(account.resets_at) }}</span>
                <span v-else>Date de reset inconnue</span>
              </p>
              <span
                class="inline-flex items-center gap-1 self-end text-sm font-medium text-[var(--app-ink)] transition group-hover:gap-1.5"
              >
                Voir les identifiants
                <UIcon name="i-lucide-arrow-right" class="h-3.5 w-3.5" />
              </span>
            </div>
          </UCard>
        </button>
      </div>
    </template>

    <CursorAccountCredentialsDrawer
      :open="credentialsOpen"
      :account="selectedAccount"
      @close="credentialsOpen = false"
      @edit="openEditFromCredentials"
    />
    <CursorAccountFormDrawer
      :open="formOpen"
      :mode="formMode"
      :account="selectedAccount"
      @close="formOpen = false"
      @saved="onSaved"
    />
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import type { CursorAccount, CursorAccountsOverview } from '~/types'
import {
  deleteCursorAccount,
  importMachineCursorSession,
  listCursorAccounts,
  refreshCursorAccounts,
} from '~/services/cursorAccountsService'
import { formatDateTimeFr, parseApiDateTime } from '~/utils/datetime'

definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const overview = ref<CursorAccountsOverview | null>(null)
const loading = ref(false)
const refreshing = ref(false)
const importing = ref(false)
const bannerError = ref<string | null>(null)

/**
 * Hide import once the live machine session is vaulted (API auto-syncs it).
 * The live account is only hidden visually from the registered list (by email).
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
  // Live pinned session with email → treated as already present (no manual import).
  if (data.machine?.source === 'live' && machineEmail) return false
  return true
})

const credentialsOpen = ref(false)
const formOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const selectedAccount = ref<CursorAccount | null>(null)

const toast = useToast()

/**
 * Compact percent label.
 */
function pctLabel(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)} %`
}

/**
 * Initials for the avatar fallback (from email local-part).
 */
function avatarInitials(email?: string | null): string {
  if (!email) return 'C'
  const local = email.split('@')[0] || email
  const parts = local.split(/[._+-]/).filter(Boolean)
  if (parts.length >= 2) {
    return `${parts[0]![0] ?? ''}${parts[1]![0] ?? ''}`.toUpperCase()
  }
  return local.slice(0, 2).toUpperCase()
}

/**
 * Best-effort avatar URL (UI Avatars — Cursor does not expose a local profile photo).
 */
function gravatarUrl(email?: string | null): string | undefined {
  if (!email) return undefined
  const name = encodeURIComponent(email.split('@')[0] || email)
  return `https://ui-avatars.com/api/?name=${name}&background=52525b&color=fff&size=128&bold=true`
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
function isFull(account: CursorAccount): boolean {
  const avg = account.average_utilization
  return avg != null && avg >= 0.999
}

/**
 * Whether the account still has headroom.
 */
function hasRoom(account: CursorAccount): boolean {
  const avg = account.average_utilization
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
    overview.value = await listCursorAccounts()
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
    overview.value = await refreshCursorAccounts()
    toast.add({ title: 'Quotas actualisés', color: 'success' })
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : 'Actualisation impossible'
  } finally {
    refreshing.value = false
  }
}

/**
 * Import local IDE session into the vault.
 */
async function importMachine(): Promise<void> {
  importing.value = true
  bannerError.value = null
  try {
    await importMachineCursorSession()
    overview.value = await listCursorAccounts()
    if (overview.value) {
      overview.value.machine_imported = true
    }
    toast.add({ title: 'Session machine importée', color: 'success' })
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : 'Import impossible'
  } finally {
    importing.value = false
  }
}

function openCreate(): void {
  formMode.value = 'create'
  selectedAccount.value = null
  formOpen.value = true
}

function openCredentials(account: CursorAccount): void {
  selectedAccount.value = account
  credentialsOpen.value = true
}

function openEditFromCredentials(): void {
  credentialsOpen.value = false
  formMode.value = 'edit'
  formOpen.value = true
}

async function onSaved(): Promise<void> {
  overview.value = await listCursorAccounts()
}

async function removeAccount(account: CursorAccount): Promise<void> {
  if (!confirm(`Supprimer le compte « ${account.email || account.label} » ?`)) return
  try {
    await deleteCursorAccount(account.id)
    overview.value = await listCursorAccounts()
    toast.add({ title: 'Compte supprimé', color: 'neutral' })
  } catch (err) {
    bannerError.value = err instanceof Error ? err.message : 'Suppression impossible'
  }
}

onMounted(() => {
  void load()
})
</script>
