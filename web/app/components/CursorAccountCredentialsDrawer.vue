<template>
  <AppDrawer
    :open="open"
    :title="account?.email || 'Compte Cursor'"
    subtitle="Identifiants de connexion"
    @close="emit('close')"
  >
    <template #icon>
      <CursorLogo class="h-5 w-5 text-[var(--app-ink)]" />
    </template>
    <div v-if="loading" class="flex justify-center py-10">
      <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
    </div>

    <div
      v-else-if="error"
      class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-200"
    >
      {{ error }}
    </div>

    <div v-else class="flex flex-col gap-4">
      <p class="text-sm text-[var(--app-ink-soft)]">
        Rappel pour te reconnecter sur
        <a
          href="https://cursor.com"
          target="_blank"
          rel="noopener noreferrer"
          class="text-[var(--app-accent)] underline-offset-2 hover:underline"
        >
          cursor.com
        </a>
        .
      </p>

      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-[var(--app-ink)]">Email</label>
        <div class="flex gap-2">
          <UInput :model-value="credentials?.email || ''" class="w-full" readonly placeholder="—" />
          <UButton
            color="neutral"
            variant="outline"
            icon="i-lucide-copy"
            :disabled="!credentials?.email"
            title="Copier"
            @click="copy(credentials?.email)"
          />
        </div>
      </div>

      <div class="flex flex-col gap-1.5">
        <label class="text-sm font-medium text-[var(--app-ink)]">Mot de passe</label>
        <div class="flex gap-2">
          <UInput
            :model-value="credentials?.password || ''"
            class="w-full"
            :type="showPassword ? 'text' : 'password'"
            readonly
            placeholder="Aucun mot de passe enregistré"
          />
          <UButton
            color="neutral"
            variant="outline"
            :icon="showPassword ? 'i-lucide-eye-off' : 'i-lucide-eye'"
            :disabled="!credentials?.password"
            title="Afficher / masquer"
            @click="showPassword = !showPassword"
          />
          <UButton
            color="neutral"
            variant="outline"
            icon="i-lucide-copy"
            :disabled="!credentials?.password"
            title="Copier"
            @click="copy(credentials?.password)"
          />
        </div>
      </div>

      <p v-if="copied" class="text-xs text-[var(--app-accent)]">Copié dans le presse-papiers.</p>
    </div>

    <template #footer>
      <UButton color="neutral" variant="outline" class="flex-1" @click="emit('close')">Fermer</UButton>
      <UButton color="neutral" variant="soft" class="flex-1" icon="i-lucide-pencil" @click="emit('edit')">
        Modifier
      </UButton>
    </template>
  </AppDrawer>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue'
import type { CursorAccount, CursorAccountCredentials } from '~/types'
import { fetchCursorCredentials } from '~/services/cursorAccountsService'

const props = defineProps<{
  open: boolean
  account: CursorAccount | null
}>()

const emit = defineEmits<{
  close: []
  edit: []
}>()

const loading = ref(false)
const error = ref<string | null>(null)
const credentials = ref<CursorAccountCredentials | null>(null)
const showPassword = ref(false)
const copied = ref(false)
let copiedTimer: ReturnType<typeof setTimeout> | null = null

/**
 * Load decrypted credentials when the drawer opens.
 */
async function load(): Promise<void> {
  if (!props.account) return
  loading.value = true
  error.value = null
  credentials.value = null
  showPassword.value = false
  try {
    credentials.value = await fetchCursorCredentials(props.account.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Impossible de lire les identifiants'
  } finally {
    loading.value = false
  }
}

/**
 * Copy text to the clipboard.
 */
async function copy(value?: string | null): Promise<void> {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    copied.value = true
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => {
      copied.value = false
    }, 1800)
  } catch {
    error.value = 'Copie impossible'
  }
}

watch(
  () => [props.open, props.account?.id] as const,
  ([open]) => {
    if (open && props.account) {
      void load()
    }
  },
)
</script>
