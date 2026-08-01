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
        v-if="working"
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
        :run-status="working ? 'RUNNING' : null"
      />
    </div>

    <!-- Composer -->
    <footer
      class="shrink-0 border-t border-[var(--app-line)] bg-[var(--app-surface)] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-5 sm:pt-3.5 sm:pb-4"
    >
      <ChatComposer
        v-model:text="newMessageText"
        v-model:provider="provider"
        v-model:model="model"
        v-model:effort="effort"
        v-model:fast-mode="fast"
        :can-send="canSend"
        :loading="sending"
        :placeholder="t('chat.session.placeholder')"
        allow-images
        @send="send"
      />
    </footer>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { AiProvider } from '~/constants/modelPresets'
import type { ComposerImage, RunEvent, RunMessage, SessionTranscript } from '~/types'
import { ensureProjectForPath, getSessionTranscript } from '~/services/machinesService'
import { addRunMessage, createConversation, listRunEvents, listRunMessages } from '~/services/runsService'

/**
 * On-PC Claude session — full history rebuilt from the transcript, continued in place
 * (each new message resumes `claude --resume`, which appends to the same session file).
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const route = useRoute()
const toast = useToast()
const activity = useSessionActivityStore()

const machineId = Number(route.params.machineId)
const sessionId = String(route.params.sessionId)

const transcript = ref<SessionTranscript | null>(null)
const loading = ref(true)
const activeRunId = ref<number | null>(null)
const awaitingReply = ref(false)
const pendingUserMessage = ref<{ text: string; images: string[] } | null>(null)
const liveEvents = ref<RunEvent[]>([])
const preSendTurnCount = ref(0)
const newMessageText = ref('')
const provider = ref<AiProvider | null>('claude')
const model = ref<string | null>('sonnet')
const effort = ref<string | null>('max')
const fast = ref(false)
const sending = ref(false)
const threadEl = ref<HTMLElement | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null
let lastEventId = 0
let replyMessageId: number | null = null
let creatingReply = false
let stopped = false
let modelPreselected = false

const canSend = computed(() => Boolean(newMessageText.value.trim()))
/** Working = my message is pending, the live feed flags it, or its last turn is in progress. */
const working = computed(() => awaitingReply.value || activity.isActive(sessionId) || Boolean(transcript.value?.active))

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
 * @param images - Optional data URLs of just-sent images (optimistic bubble only).
 * @returns The message + events pair.
 */
function toChatTurn(
  content: string,
  events: { level: string; message: string }[],
  index: number,
  running: boolean,
  images: string[] = [],
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
      images: images.length ? images : undefined,
    },
    events: events.map((event, position) => ({
      id: position,
      level: event.level,
      message: event.message,
      created_at: '',
    })),
  }
}

/**
 * Transcript turns as RunChatTurn pairs. While a reply is in flight, the history is frozen at
 * pre-send and the in-flight turn streams live from the run's events (real-time, like the run
 * view) instead of waiting on the slower on-disk transcript. The overlay is dropped once the
 * transcript has absorbed the settled turn (see loadTranscript).
 */
const turns = computed(() => {
  const source = transcript.value?.turns ?? []
  if (pendingUserMessage.value !== null) {
    const list = source
      .slice(0, preSendTurnCount.value)
      .map((turn, index) => toChatTurn(turn.content, turn.events, index, false))
    list.push(
      toChatTurn(
        pendingUserMessage.value.text,
        liveEvents.value.map((event) => ({ level: event.level, message: event.message })),
        preSendTurnCount.value,
        awaitingReply.value,
        pendingUserMessage.value.images,
      ),
    )
    return list
  }
  return source.map((turn, index) =>
    toChatTurn(turn.content, turn.events, index, working.value && index === source.length - 1),
  )
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
    // Pre-select the composer with the model the session actually used (once — never override a
    // manual change the user made afterwards).
    if (!modelPreselected && fresh.model) {
      provider.value = 'claude'
      model.value = fresh.model
      modelPreselected = true
    }
    // Hand the live overlay off to the transcript only once the reply is finished and its
    // settled turn has landed — never mid-stream (the transcript turn appears partial first).
    if (!awaitingReply.value && fresh.turns.length > preSendTurnCount.value) {
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
  const fresh = await listRunEvents(activeRunId.value, lastEventId).catch(() => [])
  if (fresh.length > 0) {
    liveEvents.value.push(...fresh)
    lastEventId = fresh[fresh.length - 1]!.id
  }
  // Don't conclude "done" until this reply's message actually exists — otherwise a poll racing
  // the send would read the previous reply's terminal status and cut the stream short.
  if (creatingReply) {
    return
  }
  const replyMessage =
    replyMessageId !== null ? messages.find((message) => message.id === replyMessageId) : messages[messages.length - 1]
  if (
    replyMessage &&
    (replyMessage.status === 'DONE' || replyMessage.status === 'FAILED' || replyMessage.status === 'SKIPPED')
  ) {
    awaitingReply.value = false
  }
}

/**
 * Whether the thread is scrolled near the bottom — so streaming keeps it pinned, but a manual
 * scroll up to read history is respected.
 * @returns True when within ~120px of the bottom.
 */
function isNearBottom(): boolean {
  const el = threadEl.value
  if (!el) {
    return true
  }
  return el.scrollHeight - el.scrollTop - el.clientHeight < 120
}

/**
 * Poll the transcript (and the run when continuing), then keep the view pinned to the bottom
 * whenever the user was already there — covering same-turn content growth, not just new turns.
 * @returns Nothing.
 */
async function poll(): Promise<void> {
  const stick = isNearBottom()
  await loadTranscript()
  await pollRun()
  if (stick) {
    await scrollThread()
  }
}

/**
 * Send a message: resume the session (first send creates the run, later ones append).
 * @param images - Optional compressed image attachments from the composer.
 * @returns Nothing.
 */
async function send(images: ComposerImage[] = []): Promise<void> {
  const text = newMessageText.value.trim()
  if ((!text && !images.length) || sending.value) {
    return
  }
  const content = text || t('chat.session.imageOnly')
  const payloadImages = images.map((image) => ({
    mime: image.mime,
    data: image.base64,
    filename: image.name,
  }))
  sending.value = true
  preSendTurnCount.value = transcript.value?.turns.length ?? 0
  pendingUserMessage.value = { text, images: images.map((image) => image.dataUrl) }
  liveEvents.value = []
  lastEventId = 0
  awaitingReply.value = true
  creatingReply = true
  newMessageText.value = ''
  await scrollThread()
  try {
    // Auto-link the session's folder as a NightForge project on the first reply.
    let projectId = transcript.value?.project_id ?? null
    if (!projectId && transcript.value?.cwd) {
      const project = await ensureProjectForPath(machineId, transcript.value.cwd)
      projectId = project.id
      if (transcript.value) {
        transcript.value.project_id = project.id
        transcript.value.project_name = project.name
      }
    }
    if (!projectId) {
      throw new Error('project-unresolved')
    }
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
          images: payloadImages,
        },
      })
      activeRunId.value = run.id
      replyMessageId = null
    } else {
      const created = await addRunMessage(activeRunId.value, {
        project_id: projectId,
        content,
        claude_session_id: sessionId,
        provider: 'claude',
        claude_model: model.value,
        effort: effort.value,
        fast_mode: fast.value,
        images: payloadImages,
      })
      replyMessageId = created.id
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
    creatingReply = false
  }
}

/** Self-pacing poll: snappy (1.2s) while a reply streams, relaxed (3s) when idle. */
async function pollLoop(): Promise<void> {
  await poll()
  if (stopped) {
    return
  }
  timer = setTimeout(pollLoop, awaitingReply.value ? 1200 : 3000)
}

onMounted(async () => {
  await loadTranscript()
  loading.value = false
  await scrollThread()
  timer = setTimeout(pollLoop, awaitingReply.value ? 1200 : 3000)
})

onBeforeUnmount(() => {
  stopped = true
  if (timer) clearTimeout(timer)
})
</script>
