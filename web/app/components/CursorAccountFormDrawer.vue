<template>
  <AppDrawer
    :open="open"
    :title="mode === 'create' ? 'Ajouter un compte Cursor' : 'Modifier le compte'"
    subtitle="Email / mot de passe en rappel chiffré"
    @close="onClose"
  >
    <template #icon>
      <CursorLogo class="h-5 w-5 text-[var(--app-ink)]" />
    </template>

    <form id="cursor-account-form" class="flex flex-col gap-4" @submit.prevent="submit">
      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-[var(--app-ink)]">Email Cursor</label>
        <UInput v-model="form.email" type="email" required placeholder="toi@exemple.com" autofocus />
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-[var(--app-ink)]">
          Mot de passe
          <span class="font-normal text-[var(--app-ink-soft)]">(rappel chiffré)</span>
        </label>
        <UInput
          v-model="form.password"
          type="password"
          :placeholder="mode === 'edit' && account?.has_password ? 'Laisser vide pour ne pas changer' : '••••••••'"
        />
      </div>

      <div v-if="!loginId && !sessionReady">
        <button
          type="button"
          class="flex w-full cursor-pointer items-center justify-center gap-2.5 rounded-lg bg-[#141414] px-4 py-2.5 text-sm font-medium text-white transition hover:bg-black disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-[#141414] dark:hover:bg-zinc-100"
          :disabled="loginStarting"
          @click="startLogin"
        >
          <UIcon v-if="loginStarting" name="i-lucide-loader-circle" class="h-4 w-4 animate-spin" />
          <CursorLogo v-else class="h-4 w-4" />
          <span>{{ loginStarting ? 'Ouverture…' : 'Se connecter avec Cursor' }}</span>
        </button>
      </div>

      <div v-else-if="loginId && !sessionReady" class="flex flex-col gap-2">
        <div
          class="flex items-center justify-center gap-2 rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] px-4 py-2.5 text-sm font-medium text-[var(--app-ink)]"
        >
          <UIcon name="i-lucide-loader-circle" class="h-4 w-4 animate-spin text-[var(--app-ink-soft)]" />
          <span>{{ loginStatusLabel }}</span>
        </div>
        <div class="flex justify-end">
          <UButton type="button" color="neutral" variant="ghost" size="sm" @click="cancelLogin"> Annuler </UButton>
        </div>
      </div>

      <p
        v-if="sessionReady"
        class="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-700 dark:text-emerald-300"
      >
        Session récupérée
        <template v-if="form.email"> pour {{ form.email }}</template>
        — tu peux enregistrer.
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
              Token de session
              <span class="font-normal text-[var(--app-ink-soft)]">(quotas)</span>
            </label>
            <UTextarea
              v-model="form.session_token"
              :rows="3"
              autoresize
              :placeholder="
                mode === 'edit' && account?.has_session_token && !form.session_token
                  ? 'Déjà enregistré — laisse vide pour conserver, ou colle un nouveau token'
                  : 'Rempli auto après connexion — ou colle WorkosCursorSessionToken'
              "
            />
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="text-sm font-medium text-[var(--app-ink)]">
              API key
              <span class="font-normal text-[var(--app-ink-soft)]">(optionnel, CLI)</span>
            </label>
            <UInput
              v-model="form.api_key"
              type="password"
              :placeholder="mode === 'edit' && account?.has_api_key ? 'Laisser vide pour conserver' : 'key_…'"
            />
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
        form="cursor-account-form"
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
import type { CursorAccount } from '~/types'
import {
  cancelCursorLogin,
  createCursorAccount,
  pollCursorLogin,
  startCursorLogin,
  updateCursorAccount,
} from '~/services/cursorAccountsService'

const props = defineProps<{
  open: boolean
  mode: 'create' | 'edit'
  account?: CursorAccount | null
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
let pollTimer: ReturnType<typeof setInterval> | null = null
let consecutivePollFailures = 0

const form = reactive({
  email: '',
  password: '',
  session_token: '',
  api_key: '',
})

const loginStatusLabel = computed(() =>
  loginPhase.value === 'capturing' ? 'Connexion en cours…' : 'En attente de connexion…',
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
  consecutivePollFailures = 0
  if (props.mode === 'edit' && props.account) {
    form.email = props.account.email || ''
    form.password = ''
    form.session_token = ''
    form.api_key = ''
  } else {
    form.email = ''
    form.password = ''
    form.session_token = ''
    form.api_key = ''
  }
}

function stopPolling(): void {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

/**
 * Start NoDriver capture (agent opens isolated Chrome).
 */
async function startLogin(): Promise<void> {
  loginStarting.value = true
  error.value = null
  loginPhase.value = 'waiting'
  consecutivePollFailures = 0
  try {
    const started = await startCursorLogin()
    if (started.status === 'ready' && started.session_token) {
      applyCapturedSession(started.session_token, started.email)
      return
    }
    loginId.value = started.login_id
    stopPolling()
    pollTimer = setInterval(() => {
      void silentPoll()
    }, 2000)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Impossible de démarrer la capture Cursor'
  } finally {
    loginStarting.value = false
  }
}

async function silentPoll(): Promise<void> {
  if (!loginId.value || sessionReady.value) return
  try {
    const result = await pollCursorLogin(loginId.value)
    consecutivePollFailures = 0
    if (result.status === 'ready' && result.session_token) {
      loginPhase.value = 'capturing'
      applyCapturedSession(result.session_token, result.email)
    } else if (result.status === 'error' && result.error) {
      error.value = result.error
      stopPolling()
      loginId.value = null
    } else if ((result.elapsed_seconds || 0) > 3) {
      // Cookie not yet present — keep waiting label (auto-capture).
      loginPhase.value = 'waiting'
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : ''
    // API reload / brief WS drop is common during login — keep polling.
    if (/timeout|hors ligne|offline|aucune machine|n’a pas répondu|n'a pas répondu/i.test(message)) {
      consecutivePollFailures += 1
      if (consecutivePollFailures >= 8) {
        error.value = message || 'Agent hors ligne pendant la connexion — rouvre NightForge Desktop et réessaie.'
        stopPolling()
        loginId.value = null
      }
      return
    }
  }
}

/**
 * Apply a captured session into the form (advanced fields prefilled).
 */
function applyCapturedSession(token: string, email?: string | null): void {
  form.session_token = token
  if (email) {
    form.email = email
  }
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
      await cancelCursorLogin(id)
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
 * Create or update the account.
 */
async function submit(): Promise<void> {
  const email = form.email.trim()
  if (!email) return
  if (props.mode === 'create' && !form.session_token.trim() && !sessionReady.value) {
    error.value = 'Connecte-toi avec Cursor (ou renseigne un token en Avancé) avant d’enregistrer.'
    return
  }
  saving.value = true
  error.value = null
  try {
    if (props.mode === 'create') {
      await createCursorAccount({
        email,
        password: form.password || null,
        session_token: form.session_token.trim() || null,
        api_key: form.api_key.trim() || null,
      })
    } else if (props.account) {
      await updateCursorAccount(props.account.id, {
        email,
        ...(form.password ? { password: form.password } : {}),
        ...(form.session_token.trim() ? { session_token: form.session_token.trim() } : {}),
        ...(form.api_key.trim() ? { api_key: form.api_key.trim() } : {}),
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
