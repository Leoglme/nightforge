<template>
  <div class="flex min-h-0 flex-1 flex-col bg-[var(--app-bg)]">
    <!-- Top bar -->
    <header
      class="flex shrink-0 items-center gap-2 border-b border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-2 sm:gap-3 sm:px-5 sm:py-2.5"
    >
      <UButton
        size="sm"
        color="neutral"
        variant="ghost"
        icon="i-lucide-arrow-left"
        to="/dashboard/chat"
        :aria-label="t('nav.back')"
      />
      <ClaudeLogo class="!h-4 !w-4 shrink-0" />
      <h1 class="truncate text-base font-semibold tracking-[-0.02em] text-[var(--app-ink)] sm:text-lg">
        {{ headerTitle }}
      </h1>
      <span
        v-if="awaitingReply"
        class="ml-auto inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-[var(--app-accent-ink)]"
      >
        <UIcon name="i-lucide-loader-circle" class="h-3.5 w-3.5 animate-spin" />
        {{ t('runs.chat.thinking') }}
      </span>
    </header>

    <!-- Chat thread -->
    <div
      ref="threadEl"
      class="app-scroll min-h-0 flex-1 space-y-8 overflow-y-auto overscroll-contain px-3 py-4 sm:space-y-10 sm:px-5 sm:py-6"
    >
      <div v-if="loading" class="flex justify-center py-10">
        <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
      </div>

      <div
        v-else-if="!turns.length"
        class="mx-auto flex max-w-md flex-col items-center gap-2 rounded-2xl border border-dashed border-[var(--app-line)] px-4 py-10 text-center"
      >
        <UIcon name="i-lucide-messages-square" class="h-7 w-7 text-[var(--app-ink-soft)]" />
        <p class="text-sm font-medium text-[var(--app-ink)]">{{ t('chat.session.emptyTitle') }}</p>
      </div>

      <RunChatTurn
        v-for="turn in turns"
        :key="turn.message.id"
        :message="turn.message"
        :events="turn.events"
        :run-status="awaitingReply ? 'RUNNING' : null"
      />
    </div>

    <!-- Composer -->
    <footer
      class="shrink-0 border-t border-[var(--app-line)] bg-[var(--app-surface)] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-5 sm:pt-3.5 sm:pb-4"
    >
      <div
        v-if="!loading && !canResume"
        class="mx-auto max-w-3xl rounded-xl border border-dashed border-[var(--app-line)] px-4 py-3 text-center text-xs text-[var(--app-ink-soft)]"
      >
        {{ t('chat.session.unregisteredHint') }}
      </div>
      <ChatComposer
        v-else
        v-model:text="newMessageText"
        v-model:provider="provider"
        v-model:model="model"
        v-model:effort="effort"
        v-model:fast-mode="fast"
        :can-send="canSend"
        :loading="sending"
        :placeholder="t('chat.session.placeholder')"
        @send="send"
      />
    </footer>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { AiProvider } from '~/constants/modelPresets'
import type { RunEvent, RunMessage, SessionTranscript } from '~/types'
import { getSessionTranscript } from '~/services/machinesService'
import { addRunMessage, createConversation, listRunMessages } from '~/services/runsService'

/**
 * On-PC Claude session — full history rebuilt from the transcript, continued in place
 * (each new message resumes `claude --resume`, which appends to the same session file).
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const route = useRoute()
const toast = useToast()

const machineId = Number(route.params.machineId)
const sessionId = String(route.params.sessionId)

const transcript = ref<SessionTranscript | null>(null)
const loading = ref(true)
const activeRunId = ref<number | null>(null)
const awaitingReply = ref(false)
const pendingUserMessage = ref<string | null>(null)
const preSendTurnCount = ref(0)
const newMessageText = ref('')
const provider = ref<AiProvider | null>('claude')
const model = ref<string | null>('sonnet')
const effort = ref<string | null>('max')
const fast = ref(false)
const sending = ref(false)
const threadEl = ref<HTMLElement | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const canResume = computed(() => Boolean(transcript.value?.project_id))
const canSend = computed(() => Boolean(newMessageText.value.trim() && canResume.value))

const headerTitle = computed(() => {
  const name = transcript.value?.project_name
  if (name) {
    return name
  }
  const cwd = transcript.value?.cwd
  return cwd?.split(/[\\/]/).filter(Boolean).pop() || t('chat.session.title')
})

/**
 * Build a RunChatTurn-compatible message/events pair from a transcript turn.
 * @param content - The user prompt.
 * @param events - The assistant text / encoded tool actions.
 * @param index - Turn index (stable key).
 * @param running - Whether this turn is the in-progress reply.
 * @returns The message + events pair.
 */
function toChatTurn(
  content: string,
  events: { level: string; message: string }[],
  index: number,
  running: boolean,
): { message: RunMessage; events: RunEvent[] } {
  return {
    message: {
      id: index,
      run_id: 0,
      project_id: transcript.value?.project_id ?? 0,
      order_index: index,
      content,
      claude_model: null,
      provider: 'claude',
      status: running ? 'RUNNING' : 'DONE',
      created_at: '',
    },
    events: events.map((event, position) => ({
      id: position,
      level: event.level,
      message: event.message,
      created_at: '',
    })),
  }
}

/** Transcript turns as RunChatTurn pairs, plus an optimistic bubble for a just-sent message. */
const turns = computed(() => {
  const source = transcript.value?.turns ?? []
  const list = source.map((turn, index) =>
    toChatTurn(
      turn.content,
      turn.events,
      index,
      awaitingReply.value && !pendingUserMessage.value && index === source.length - 1,
    ),
  )
  if (awaitingReply.value && pendingUserMessage.value !== null) {
    list.push(toChatTurn(pendingUserMessage.value, [], source.length, true))
  }
  return list
})

/**
 * Scroll the thread to the newest message.
 * @returns Nothing.
 */
async function scrollThread(): Promise<void> {
  await nextTick()
  if (threadEl.value) {
    threadEl.value.scrollTop = threadEl.value.scrollHeight
  }
}

/**
 * Reload the transcript from the machine and clear the optimistic bubble once it lands.
 * @returns Nothing.
 */
async function loadTranscript(): Promise<void> {
  const fresh = await getSessionTranscript(machineId, sessionId).catch(() => null)
  if (fresh) {
    transcript.value = fresh
    if (fresh.turns.length > preSendTurnCount.value) {
      pendingUserMessage.value = null
    }
  }
}

/**
 * Poll the active resume run to know when the reply is finished.
 * @returns Nothing.
 */
async function pollRun(): Promise<void> {
  if (!activeRunId.value) {
    return
  }
  const messages = await listRunMessages(activeRunId.value).catch(() => [])
  const last = messages[messages.length - 1]
  if (last && (last.status === 'DONE' || last.status === 'FAILED' || last.status === 'SKIPPED')) {
    awaitingReply.value = false
  }
}

/**
 * Poll the transcript (and the run when continuing), then keep the view pinned to the bottom.
 * @returns Nothing.
 */
async function poll(): Promise<void> {
  const previousTurns = transcript.value?.turns.length ?? 0
  await loadTranscript()
  await pollRun()
  if ((transcript.value?.turns.length ?? 0) !== previousTurns) {
    await scrollThread()
  }
}

/**
 * Send a message: resume the session (first send creates the run, later ones append).
 * @returns Nothing.
 */
async function send(): Promise<void> {
  const content = newMessageText.value.trim()
  const projectId = transcript.value?.project_id
  if (!content || !projectId || sending.value) {
    return
  }
  sending.value = true
  preSendTurnCount.value = transcript.value?.turns.length ?? 0
  pendingUserMessage.value = content
  awaitingReply.value = true
  newMessageText.value = ''
  await scrollThread()
  try {
    if (!activeRunId.value) {
      const run = await createConversation({
        machine_id: machineId,
        project_id: projectId,
        first_message: {
          content,
          provider: 'claude',
          claude_model: model.value,
          effort: effort.value,
          fast_mode: fast.value,
          claude_session_id: sessionId,
        },
      })
      activeRunId.value = run.id
    } else {
      await addRunMessage(activeRunId.value, {
        project_id: projectId,
        content,
        claude_session_id: sessionId,
        provider: 'claude',
        claude_model: model.value,
        effort: effort.value,
        fast_mode: fast.value,
      })
    }
  } catch (err) {
    awaitingReply.value = false
    pendingUserMessage.value = null
    toast.add({
      title: t('runs.chat.sendFailed'),
      description: err instanceof Error ? err.message : undefined,
      color: 'error',
    })
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  await loadTranscript()
  loading.value = false
  await scrollThread()
  timer = setInterval(poll, 3000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
