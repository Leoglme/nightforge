<template>
  <div class="flex flex-col gap-6">
    <div class="flex items-center justify-between gap-3">
      <div>
        <h1 class="app-page-title">{{ t('nav.machines') }}</h1>
        <p class="text-xs text-[var(--app-ink-soft)] sm:text-sm">
          Chaque PC qui exécute Claude Code est une machine.
          <template v-if="isDesktopApp">Un clic suffit pour connecter celui-ci.</template>
          <template v-else>Depuis l'app desktop, un clic suffit pour connecter le PC.</template>
        </p>
      </div>
      <UButton
        v-if="isDesktopApp"
        color="neutral"
        variant="outline"
        icon="i-lucide-refresh-cw"
        class="shrink-0"
        :loading="restartingAgent"
        @click="restartAgent"
      >
        <span class="hidden sm:inline">Redémarrer l'agent</span>
      </UButton>
      <UButton
        v-if="isDesktopApp"
        color="primary"
        icon="i-lucide-monitor-check"
        class="shrink-0"
        :loading="provisioning"
        @click="provision"
      >
        <span class="hidden sm:inline">Ajouter cette machine</span>
        <span class="sm:hidden">Ajouter</span>
      </UButton>
      <UButton v-else color="neutral" variant="outline" icon="i-lucide-plus" class="shrink-0" @click="openCreate">
        <span class="hidden sm:inline">Ajouter manuellement</span>
        <span class="sm:hidden">Ajouter</span>
      </UButton>
    </div>

    <UAlert
      v-if="provisionMessage"
      :color="provisionError ? 'error' : 'success'"
      variant="subtle"
      :icon="provisionError ? 'i-lucide-triangle-alert' : 'i-lucide-check-circle-2'"
      :title="provisionError ? 'Échec de la configuration' : 'Agent local'"
      :description="provisionMessage"
      :close="true"
      @update:open="provisionMessage = ''"
    />

    <UAlert
      v-if="isDesktopApp && desktopDiag"
      color="neutral"
      variant="subtle"
      icon="i-lucide-activity"
      title="Diagnostic de ce PC"
    >
      <template #description>
        <ul class="mt-1 space-y-1 text-sm text-[var(--app-ink-soft)]">
          <li>
            Nom détecté : <span class="font-medium text-[var(--app-ink)]">{{ localHostname || '—' }}</span>
          </li>
          <li>
            Agent embarqué :
            <span class="font-medium" :class="desktopDiag.sidecarRunning ? 'text-green-400' : 'text-amber-400'">
              {{ desktopDiag.sidecarRunning ? 'processus lancé' : 'processus absent' }}
            </span>
          </li>
          <li v-if="provisionedMachineId">
            Machine configurée : ID {{ provisionedMachineId }}
            <span v-if="localMachine">({{ localMachine.name }})</span>
          </li>
          <li v-if="desktopDiag.lastError" class="text-amber-300">Dernière erreur : {{ desktopDiag.lastError }}</li>
          <li class="text-xs">
            Journal agent : <code class="app-inline-code">%USERPROFILE%\.nightforge\agent.log</code>
          </li>
          <li v-if="agentLogTail" class="mt-2">
            <pre
              class="max-h-40 overflow-auto rounded border border-[var(--app-line)] bg-[var(--app-surface-2)] p-2 text-[0.65rem] leading-relaxed whitespace-pre-wrap"
              >{{ agentLogTail }}</pre>
          </li>
        </ul>
      </template>
    </UAlert>

    <div v-if="machines.length === 0" class="app-card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <UIcon name="i-lucide-monitor-off" class="text-3xl text-[var(--app-ink-soft)]" />
      <template v-if="isDesktopApp">
        <p class="max-w-sm text-sm text-[var(--app-ink-soft)]">
          Aucune machine connectée. Un seul clic : NightForge enregistre ce PC et démarre l'agent automatiquement.
        </p>
        <UButton color="primary" icon="i-lucide-monitor-check" :loading="provisioning" @click="provision">
          Ajouter cette machine
        </UButton>
      </template>
      <template v-else>
        <p class="max-w-sm text-sm text-[var(--app-ink-soft)]">
          Aucune machine enregistrée. Ouvre NightForge sur ton PC et clique « Ajouter cette machine » — tout se
          configure tout seul. (Ou ajoute-la manuellement ci-dessous.)
        </p>
        <UButton color="neutral" variant="outline" icon="i-lucide-plus" @click="openCreate">
          Ajouter manuellement
        </UButton>
      </template>
    </div>

    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <UCard
        v-for="machine in machines"
        :key="machine.id"
        :class="isLocalMachine(machine) ? 'ring-1 ring-[var(--app-accent)]' : ''"
      >
        <div class="flex items-start justify-between">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <div class="truncate font-medium">{{ machine.name }}</div>
              <span
                v-if="isLocalMachine(machine)"
                class="shrink-0 rounded bg-[var(--app-accent-soft)] px-1.5 py-0.5 text-[0.65rem] font-medium text-[var(--app-accent-ink)]"
              >
                Ce PC
              </span>
            </div>
            <div class="text-xs text-[var(--app-ink-soft)]">Agent {{ machine.agent_version ?? '—' }}</div>
          </div>
          <StatusBadge :status="machineDisplayStatus(machine)" dot />
        </div>
        <div class="mt-4 flex justify-end">
          <UButton size="sm" color="error" variant="outline" icon="i-lucide-trash-2" @click="remove(machine.id)" />
        </div>
      </UCard>
    </div>

    <AppDrawer
      :open="showCreate"
      title="Nouvelle machine"
      subtitle="Génère un token d'agent pour ce PC"
      icon="i-lucide-monitor"
      @close="closeCreate"
    >
      <div class="flex flex-col gap-5">
        <UFormField label="Nom de la machine" hint="ex. Fixe, Portable">
          <UInput v-model="name" class="w-full" size="lg" placeholder="Fixe" @keyup.enter="create" />
        </UFormField>

        <template v-if="createdToken">
          <UAlert
            color="warning"
            variant="subtle"
            icon="i-lucide-key-round"
            title="Token agent — copie-le maintenant"
            description="Il ne sera plus jamais affiché. Colle-le dans le fichier .env de l'agent (NF_AGENT_TOKEN)."
          />
          <div class="flex items-stretch gap-2">
            <code
              class="min-w-0 flex-1 truncate rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] px-3 py-2 font-mono text-xs"
            >
              {{ createdToken }}
            </code>
            <UButton
              color="neutral"
              variant="outline"
              :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
              @click="copyToken"
            />
          </div>

          <div class="rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] p-4 text-sm">
            <p class="mb-2 font-medium">Étapes sur ce PC :</p>
            <ol class="list-decimal space-y-1.5 pl-5 text-[var(--app-ink-soft)]">
              <li>
                Dans le dossier <code class="app-inline-code">agent/</code>, copie
                <code class="app-inline-code">.env.example</code> en <code class="app-inline-code">.env</code>.
              </li>
              <li>
                Renseigne <code class="app-inline-code">NF_AGENT_TOKEN</code> avec le token ci-dessus et
                <code class="app-inline-code">NF_API_BASE={{ apiBase }}</code
                >.
              </li>
              <li>Lance l'agent : <code class="app-inline-code">python -m nightforge_agent</code>.</li>
            </ol>
          </div>
        </template>
      </div>

      <template #footer>
        <UButton color="neutral" variant="outline" class="flex-1" @click="closeCreate">
          {{ createdToken ? 'Fermer' : 'Annuler' }}
        </UButton>
        <UButton
          v-if="!createdToken"
          color="primary"
          class="flex-1"
          :disabled="!name.trim()"
          :loading="creating"
          @click="create"
        >
          Générer le token
        </UButton>
      </template>
    </AppDrawer>
  </div>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Machine } from '~/types'
import { createMachine, deleteMachine, listMachines } from '~/services/machinesService'

/**
 * Machines management — register agents and view their live status.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const toast = useToast()
const config = useRuntimeConfig()
const apiBase = config.public.apiBase
const {
  isDesktopApp,
  provisionThisMachine,
  restartLocalAgent,
  detectMachineName,
  readProvisionFile,
  syncLocalAgentIfProvisioned,
  getAgentStatus,
  getAgentLogTail,
} = useMachineProvision()

const machines = ref<Machine[]>([])
const showCreate = ref(false)
const name = ref('')
const createdToken = ref<string | null>(null)
const creating = ref(false)
const copied = ref(false)
const provisioning = ref(false)
const restartingAgent = ref(false)
const provisionMessage = ref('')
const provisionError = ref(false)
const localHostname = ref('')
const provisionedMachineId = ref<number | null>(null)
const desktopDiag = ref<{ sidecarRunning: boolean; lastError: string | null } | null>(null)
const agentLogTail = ref('')
let timer: ReturnType<typeof setInterval> | null = null

const localMachine = computed(() => {
  if (provisionedMachineId.value) {
    return machines.value.find((m) => m.id === provisionedMachineId.value) ?? null
  }
  return machines.value.find((m) => m.name.toLowerCase() === localHostname.value.toLowerCase()) ?? null
})

/**
 * Whether a machine row corresponds to this desktop PC.
 * @param machine - Machine row.
 * @returns True when this is the local machine.
 */
function isLocalMachine(machine: Machine): boolean {
  if (provisionedMachineId.value && machine.id === provisionedMachineId.value) {
    return true
  }
  return machine.name.toLowerCase() === localHostname.value.toLowerCase()
}

/**
 * Badge status for a machine row (online idle machines show as ONLINE, not IDLE).
 * @param machine - Machine row.
 * @returns Status key for StatusBadge.
 */
function machineDisplayStatus(machine: Machine): string {
  if (!machine.online) {
    return 'OFFLINE'
  }
  if (machine.status === 'IDLE') {
    return 'ONLINE'
  }
  return machine.status
}

/**
 * Load hostname, provision file and sidecar diagnostics.
 * @returns Nothing.
 */
async function loadDesktopState(): Promise<void> {
  if (!isDesktopApp.value) {
    return
  }
  localHostname.value = await detectMachineName()
  const provisioned = await readProvisionFile()
  provisionedMachineId.value = typeof provisioned?.machine_id === 'number' ? provisioned.machine_id : null
  desktopDiag.value = await getAgentStatus()
  agentLogTail.value = await getAgentLogTail().catch(() => '')
}

/**
 * Poll until the local machine shows online, or timeout.
 * @param timeoutMs - Max wait in ms.
 * @returns True if online before timeout.
 */
async function waitForLocalOnline(timeoutMs = 20000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await refresh()
    if (localMachine.value?.online) {
      return true
    }
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  return false
}

/**
 * Build a helpful offline message after a failed connect attempt.
 * @returns User-facing hint.
 */
function offlineHint(): string {
  const parts = [
    'L’agent n’a pas pu se connecter à l’API.',
    'Si tu as déjà configuré l’agent manuellement, supprime les variables Windows NF_AGENT_TOKEN et NF_API_BASE (Paramètres → Système → Variables d’environnement), puis redémarre NightForge.',
    'Vérifie aussi que l’antivirus n’a pas bloqué nightforge-agent.exe.',
  ]
  if (desktopDiag.value?.lastError) {
    parts.unshift(`Erreur sidecar : ${desktopDiag.value.lastError}`)
  }
  return parts.join(' ')
}

/**
 * One-click: register this PC and configure its local agent automatically.
 * @returns Nothing.
 */
async function provision(): Promise<void> {
  if (provisioning.value) {
    return
  }
  provisioning.value = true
  provisionMessage.value = ''
  provisionError.value = false
  try {
    const hostname = await detectMachineName()
    const existing = machines.value.find((m) => m.name.toLowerCase() === hostname.toLowerCase())
    const machine = await provisionThisMachine()
    await loadDesktopState()
    provisionError.value = false
    const online = await waitForLocalOnline()
    if (online) {
      provisionMessage.value = `« ${machine.name} » est en ligne.`
    } else {
      provisionError.value = true
      provisionMessage.value = existing
        ? `« ${machine.name} » a été reconnectée mais reste hors ligne. ${offlineHint()}`
        : `« ${machine.name} » est enregistrée mais reste hors ligne. ${offlineHint()}`
    }
  } catch (error) {
    provisionError.value = true
    provisionMessage.value =
      error instanceof Error ? error.message : 'Impossible de configurer cette machine automatiquement.'
    await loadDesktopState()
  } finally {
    provisioning.value = false
  }
}

/**
 * Restart the local agent sidecar (reloads ~/.nightforge/agent.json).
 * @returns Nothing.
 */
async function restartAgent(): Promise<void> {
  if (restartingAgent.value) {
    return
  }
  restartingAgent.value = true
  provisionMessage.value = ''
  provisionError.value = false
  try {
    await restartLocalAgent()
    await loadDesktopState()
    const online = await waitForLocalOnline()
    if (online) {
      provisionError.value = false
      provisionMessage.value = 'Agent redémarré — machine en ligne.'
    } else {
      provisionError.value = true
      provisionMessage.value = `Agent redémarré mais toujours hors ligne. ${offlineHint()}`
    }
  } catch (error) {
    provisionError.value = true
    provisionMessage.value = error instanceof Error ? error.message : "Impossible de redémarrer l'agent local."
    await loadDesktopState()
  } finally {
    restartingAgent.value = false
  }
}

/**
 * Refresh the machines list.
 * @returns Nothing.
 */
async function refresh(): Promise<void> {
  machines.value = await listMachines().catch(() => [])
}

/**
 * Open the creation drawer with a clean state.
 * @returns Nothing.
 */
function openCreate(): void {
  name.value = ''
  createdToken.value = null
  copied.value = false
  showCreate.value = true
}

/**
 * Close the creation drawer.
 * @returns Nothing.
 */
function closeCreate(): void {
  showCreate.value = false
}

/**
 * Register a machine and reveal its one-time token.
 * @returns Nothing.
 */
async function create(): Promise<void> {
  if (!name.value.trim() || creating.value) {
    return
  }
  creating.value = true
  try {
    const machine = await createMachine(name.value.trim())
    createdToken.value = machine.agent_token
    await refresh()
  } finally {
    creating.value = false
  }
}

/**
 * Copy the freshly created token to the clipboard.
 * @returns Nothing.
 */
async function copyToken(): Promise<void> {
  if (!createdToken.value) {
    return
  }
  try {
    await navigator.clipboard.writeText(createdToken.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    copied.value = false
  }
}

/**
 * Delete a machine.
 * @param id - Machine id.
 * @returns Nothing.
 */
async function remove(id: number): Promise<void> {
  try {
    await deleteMachine(id)
    if (provisionedMachineId.value === id) {
      provisionedMachineId.value = null
    }
    toast.add({ title: 'Machine supprimée', color: 'success' })
    await refresh()
  } catch (error) {
    toast.add({
      title: 'Impossible de supprimer la machine',
      description: error instanceof Error ? error.message : undefined,
      color: 'error',
    })
  }
}

onMounted(async () => {
  await refresh()
  await loadDesktopState()
  if (isDesktopApp.value && !localMachine.value?.online) {
    await syncLocalAgentIfProvisioned()
    await waitForLocalOnline(15000)
    await loadDesktopState()
  }
  timer = setInterval(async () => {
    await refresh()
    if (isDesktopApp.value) {
      desktopDiag.value = await getAgentStatus()
    }
  }, 12000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
