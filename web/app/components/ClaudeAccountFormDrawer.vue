<template>
  <AppDrawer
    :open="open"
    :title="mode === 'create' ? 'Ajouter un compte Claude' : 'Modifier le compte'"
    subtitle="Connecte un compte Claude Code via OAuth"
    @close="onClose"
  >
    <template #icon>
      <ClaudeLogo class="h-5 w-5 text-[#D97757]" />
    </template>

    <form id="claude-account-form" class="flex flex-col gap-4" @submit.prevent="submit">
      <div v-if="!loginId && !sessionReady">
        <button
          type="button"
          class="flex w-full cursor-pointer items-center justify-center gap-2.5 rounded-lg bg-[#D97757] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-[#c2603f] disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="loginStarting"
          @click="startLogin"
        >
          <UIcon v-if="loginStarting" name="i-lucide-loader-circle" class="h-4 w-4 animate-spin" />
          <ClaudeLogo v-else class="h-4 w-4" />
          <span>{{ loginStarting ? 'Ouverture…' : 'Se connecter avec Claude' }}</span>
        </button>
      </div>

      <div v-else-if="loginId && !sessionReady" class="flex flex-col gap-2">
        <div
          class="flex items-center justify-center gap-2 rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] px-4 py-2.5 text-sm font-medium text-[var(--app-ink)]"
        >
          <UIcon name="i-lucide-loader-circle" class="h-4 w-4 animate-spin text-[var(--app-ink-soft)]" />
          <span>{{ loginStatusLabel }}</span>
        </div>
        <p v-if="loginNote" class="text-xs text-[var(--app-ink-soft)]">{{ loginNote }}</p>
        <a
          v-if="loginUrl"
          :href="loginUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="text-xs text-[var(--app-accent)] underline-offset-2 hover:underline"
        >
          Ouvrir la fenêtre de connexion manuellement
        </a>
        <div class="flex justify-end">
          <UButton type="button" color="neutral" variant="ghost" size="sm" @click="cancelLogin"> Annuler </UButton>
        </div>
      </div>

      <p
        v-if="sessionReady"
        class="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-700 dark:text-emerald-300"
      >
        Session récupérée — tu peux enregistrer.
      </p>

      <div>
        <button
          type="button"
          class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg px-1 py-1.5 text-left text-sm text-[var(--app-ink-soft)] transition hover:text-[var(--app-ink)]"
          @click="advancedOpen = !advancedOpen"
        >
          <span class="font-medium">Avancé</span>
          <UIcon :name="advancedOpen ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'" class="h-4 w-4" />
        </button>

        <div v-if="advancedOpen" class="mt-2 flex flex-col gap-4 border-t border-[var(--app-line)] pt-3">
          <div class="flex flex-col gap-1.5">
            <label class="text-sm font-medium text-[var(--app-ink)]">
              JSON OAuth
              <span class="font-normal text-[var(--app-ink-soft)]">(quotas)</span>
            </label>
            <UTextarea v-model="form.oauth_json" :rows="3" autoresize :placeholder="oauthJsonPlaceholder" />
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="text-sm font-medium text-[var(--app-ink)]">
              Jeton d'accès
              <span class="font-normal text-[var(--app-ink-soft)]">(alternative simple)</span>
            </label>
            <UInput v-model="form.access_token" type="password" placeholder="sk-ant-oat…" />
          </div>
        </div>
      </div>

      <p
        v-if="error"
        class="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600 dark:text-red-300"
      >
        {{ error }}
      </p>
    </form>

    <template #footer>
      <UButton color="neutral" variant="outline" class="flex-1" :disabled="saving" @click="onClose"> Annuler </UButton>
      <UButton
        type="submit"
        form="claude-account-form"
        color="primary"
        class="flex-1"
        :loading="saving"
        icon="i-lucide-check"
      >
        {{ mode === 'create' ? 'Ajouter' : 'Enregistrer' }}
      </UButton>
    </template>
  </AppDrawer>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import type { ClaudeAccount } from '~/types'
import {
  cancelClaudeLogin,
  createClaudeAccount,
  pollClaudeLogin,
  startClaudeLogin,
  updateClaudeAccount,
} from '~/services/claudeAccountsService'

const props = defineProps<{
  open: boolean
  mode: 'create' | 'edit'
  account?: ClaudeAccount | null
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const saving = ref(false)
const error = ref<string | null>(null)
const advancedOpen = ref(false)
const sessionReady = ref(false)

const loginStarting = ref(false)
const loginId = ref<string | null>(null)
const loginPhase = ref<'waiting' | 'capturing'>('waiting')
const loginUrl = ref<string | null>(null)
const loginNote = ref<string | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const form = reactive({
  oauth_json: '',
  access_token: '',
})

const loginStatusLabel = computed(() =>
  loginPhase.value === 'capturing' ? 'Connexion en cours…' : 'En attente de connexion…',
)

const oauthJsonPlaceholder = computed(() =>
  props.mode === 'edit' && props.account?.has_oauth && !form.oauth_json
    ? 'Déjà enregistré — laisse vide pour conserver, ou colle un nouveau bloc OAuth'
    : 'Rempli auto après connexion — ou colle { "accessToken": ... }',
)

/**
 * Reset the form when the drawer opens.
 */
function resetForm(): void {
  error.value = null
  sessionReady.value = false
  advancedOpen.value = false
  stopPolling()
  loginId.value = null
  loginPhase.value = 'waiting'
  loginUrl.value = null
  loginNote.value = null
  form.oauth_json = ''
  form.access_token = ''
}

function stopPolling(): void {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/**
 * Start `claude auth login` capture on the agent.
 */
async function startLogin(): Promise<void> {
  loginStarting.value = true
  error.value = null
  loginPhase.value = 'waiting'
  try {
    const started = await startClaudeLogin()
    loginId.value = started.login_id
    loginUrl.value = started.login_url || null
    loginNote.value = started.note || null
    stopPolling()
    pollTimer = setInterval(() => {
      void silentPoll()
    }, 2000)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Impossible de démarrer la capture Claude'
  } finally {
    loginStarting.value = false
  }
}

async function silentPoll(): Promise<void> {
  if (!loginId.value || sessionReady.value) return
  try {
    const result = await pollClaudeLogin(loginId.value)
    if (result.status === 'ready' && result.oauth) {
      loginPhase.value = 'capturing'
      applyCapturedSession(result.oauth)
    } else if (result.status === 'error' && result.error) {
      error.value = result.error
      stopPolling()
      loginId.value = null
    } else if ((result.elapsed_seconds || 0) > 3) {
      loginPhase.value = 'waiting'
      if (result.login_url) loginUrl.value = result.login_url
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : ''
    if (/timeout|hors ligne|offline|aucune machine/i.test(message)) {
      error.value = message
      stopPolling()
      loginId.value = null
    }
  }
}

/**
 * Apply a captured OAuth block into the form (advanced field prefilled).
 */
function applyCapturedSession(oauth: Record<string, unknown>): void {
  form.oauth_json = JSON.stringify(oauth)
  sessionReady.value = true
  advancedOpen.value = true
  stopPolling()
  loginId.value = null
  loginPhase.value = 'waiting'
}

async function cancelLogin(): Promise<void> {
  const id = loginId.value
  stopPolling()
  loginId.value = null
  loginPhase.value = 'waiting'
  if (id) {
    try {
      await cancelClaudeLogin(id)
    } catch {
      // ignore
    }
  }
}

async function onClose(): Promise<void> {
  if (loginId.value && !sessionReady.value) {
    await cancelLogin()
  } else {
    stopPolling()
  }
  emit('close')
}

/**
 * Create or update the account (OAuth only — no email / password reminder).
 */
async function submit(): Promise<void> {
  if (props.mode === 'create' && !form.oauth_json.trim() && !form.access_token.trim() && !sessionReady.value) {
    error.value = 'Connecte-toi avec Claude (ou renseigne un jeton en Avancé) avant d’enregistrer.'
    return
  }
  saving.value = true
  error.value = null
  try {
    if (props.mode === 'create') {
      await createClaudeAccount({
        oauth_json: form.oauth_json.trim() || null,
        access_token: form.access_token.trim() || null,
      })
    } else if (props.account) {
      await updateClaudeAccount(props.account.id, {
        ...(form.oauth_json.trim() ? { oauth_json: form.oauth_json.trim() } : {}),
        ...(form.access_token.trim() ? { access_token: form.access_token.trim() } : {}),
      })
    }
    emit('saved')
    emit('close')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Enregistrement impossible'
  } finally {
    saving.value = false
  }
}

watch(
  () => [props.open, props.mode, props.account?.id] as const,
  ([open]) => {
    if (open) resetForm()
  },
)

onBeforeUnmount(() => {
  stopPolling()
})
</script>
