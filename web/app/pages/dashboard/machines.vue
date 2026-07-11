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
      :title="provisionError ? 'Échec de la configuration' : 'Machine connectée'"
      :description="provisionMessage"
      :close="true"
      @update:open="provisionMessage = ''"
    />

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
      <UCard v-for="machine in machines" :key="machine.id">
        <div class="flex items-start justify-between">
          <div class="min-w-0">
            <div class="truncate font-medium">{{ machine.name }}</div>
            <div class="text-xs text-[var(--app-ink-soft)]">Agent {{ machine.agent_version ?? '—' }}</div>
          </div>
          <StatusBadge :status="machine.online ? machine.status : 'OFFLINE'" dot />
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
            <NuxtLink
              to="/dashboard/docs"
              class="mt-3 inline-flex items-center gap-1 text-xs font-medium text-[var(--app-accent-ink)] hover:underline"
            >
              Guide d'installation complet
              <UIcon name="i-lucide-arrow-right" class="h-3.5 w-3.5" />
            </NuxtLink>
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
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { Machine } from '~/types'
import { createMachine, deleteMachine, listMachines } from '~/services/machinesService'

/**
 * Machines management — register agents and view their live status.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const config = useRuntimeConfig()
const apiBase = config.public.apiBase
const { isDesktopApp, provisionThisMachine, restartLocalAgent, detectMachineName, syncLocalAgentIfProvisioned } =
  useMachineProvision()

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
let timer: ReturnType<typeof setInterval> | null = null

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
    provisionError.value = false
    provisionMessage.value = existing
      ? `« ${machine.name} » est reconnectée. L'agent redémarre et devrait passer en ligne sous quelques secondes.`
      : `« ${machine.name} » est enregistrée. L'agent redémarre et devrait passer en ligne sous quelques secondes.`
    await refresh()
  } catch (error) {
    provisionError.value = true
    provisionMessage.value =
      error instanceof Error ? error.message : 'Impossible de configurer cette machine automatiquement.'
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
    provisionMessage.value = 'Agent redémarré — connexion en cours…'
    await refresh()
  } catch (error) {
    provisionError.value = true
    provisionMessage.value = error instanceof Error ? error.message : "Impossible de redémarrer l'agent local."
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
  await deleteMachine(id)
  await refresh()
}

onMounted(async () => {
  await refresh()
  if (isDesktopApp.value) {
    const hostname = await detectMachineName()
    const localMachine = machines.value.find((m) => m.name.toLowerCase() === hostname.toLowerCase())
    if (localMachine && !localMachine.online) {
      const restarted = await syncLocalAgentIfProvisioned()
      if (restarted) {
        provisionError.value = false
        provisionMessage.value =
          'Agent local redémarré automatiquement. Si le statut reste hors ligne, clique « Redémarrer l\u2019agent » ou « Ajouter cette machine ».'
      }
    }
  }
  timer = setInterval(refresh, 5000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
