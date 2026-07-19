<template>
  <Teleport to="body">
    <Transition name="code-review-backdrop">
      <div
        v-if="open"
        class="fixed inset-0 z-[60] bg-[var(--app-overlay)] backdrop-blur-[2px]"
        aria-hidden="true"
        @click="close"
      />
    </Transition>

    <Transition name="code-review-sheet">
      <div
        v-if="open"
        class="code-review-anchor fixed inset-0 z-[70] flex items-end justify-center sm:items-center sm:p-6"
        role="presentation"
        @click.self="close"
        @keydown.esc.prevent="onEsc"
      >
        <div
          class="code-review-panel flex max-h-[92dvh] w-full flex-col rounded-t-2xl border border-[var(--app-line)] bg-[var(--app-surface)] shadow-2xl sm:max-h-[min(90vh,56rem)] sm:w-[min(100%,56rem)] sm:rounded-2xl"
          role="dialog"
          aria-modal="true"
          :aria-label="sheetTitle"
          @click.stop
        >
          <!-- Drag handle (mobile) -->
          <div class="flex justify-center pt-2 sm:hidden" aria-hidden="true">
            <span class="h-1 w-10 rounded-full bg-[var(--app-faint)] opacity-60" />
          </div>

          <!-- Header -->
          <div class="relative flex shrink-0 items-center justify-center px-4 py-3">
            <button
              type="button"
              class="absolute left-3 flex h-11 w-11 items-center justify-center rounded-full text-[var(--app-ink-soft)] transition-colors duration-200 hover:bg-[var(--app-surface-2)] hover:text-[var(--app-ink)]"
              :aria-label="view === 'detail' ? t('nav.back') : t('common.close')"
              @click="view === 'detail' ? (view = 'list') : close()"
            >
              <UIcon :name="view === 'detail' ? 'i-lucide-chevron-left' : 'i-lucide-x'" class="h-5 w-5" />
            </button>
            <h2 class="text-base font-semibold text-[var(--app-ink)]">{{ sheetTitle }}</h2>
          </div>

          <!-- List of file edits / actions -->
          <div
            v-if="view === 'list'"
            class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-[max(1rem,env(safe-area-inset-bottom))]"
          >
            <ul class="relative flex flex-col">
              <li v-for="(action, index) in actions" :key="index" class="relative">
                <!-- Timeline connector -->
                <span
                  v-if="index < actions.length - 1"
                  class="absolute top-10 bottom-0 left-[1.625rem] w-px bg-[var(--app-line)]"
                  aria-hidden="true"
                />
                <button
                  type="button"
                  class="flex min-h-14 w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors duration-200 hover:bg-[var(--app-surface-2)] focus-visible:ring-2 focus-visible:ring-[var(--app-ink-soft)] focus-visible:outline-none"
                  @click="openDetail(index)"
                >
                  <span
                    class="relative z-[1] flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[var(--app-line)] bg-[var(--app-surface)] text-[var(--app-ink)]"
                  >
                    <UIcon :name="iconFor(action.kind)" class="h-4 w-4" />
                  </span>
                  <span class="min-w-0 flex-1">
                    <span class="block text-sm font-medium text-[var(--app-ink)]">
                      {{ statusLabel(action) }}
                    </span>
                    <span
                      v-if="action.path || action.detail"
                      class="mt-0.5 block truncate font-mono text-xs text-[var(--app-ink-soft)]"
                      :title="action.path || action.detail"
                    >
                      {{ truncatePath(action.path || action.detail || '', 52) }}
                    </span>
                  </span>
                  <span
                    v-if="(action.additions || 0) > 0 || (action.deletions || 0) > 0"
                    class="inline-flex shrink-0 items-center gap-1.5 font-mono text-xs tabular-nums"
                  >
                    <span v-if="(action.additions || 0) > 0" class="text-[var(--app-green)]">
                      +{{ action.additions }}
                    </span>
                    <span v-if="(action.deletions || 0) > 0" class="text-[var(--app-red)]">
                      -{{ action.deletions }}
                    </span>
                  </span>
                </button>
              </li>
            </ul>

            <p v-if="!actions.length" class="px-4 py-8 text-center text-sm text-[var(--app-ink-soft)]">
              {{ t('runs.chat.review.empty') }}
            </p>
          </div>

          <!-- Diff / detail view -->
          <div
            v-else-if="active"
            class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-4 pb-[max(1rem,env(safe-area-inset-bottom))]"
          >
            <section v-if="active.path">
              <p class="app-label mb-1.5">{{ t('runs.chat.review.file') }}</p>
              <div
                class="rounded-xl border border-[var(--app-line)] bg-[var(--app-surface-2)] px-3 py-2.5 font-mono text-xs leading-relaxed break-all text-[var(--app-ink)] sm:text-[0.8125rem]"
              >
                {{ active.path }}
              </div>
            </section>

            <section v-if="active.kind === 'bash' && active.detail">
              <p class="app-label mb-1.5">{{ t('runs.chat.review.command') }}</p>
              <pre
                class="overflow-x-auto rounded-xl border border-[var(--app-line)] bg-[var(--app-surface-2)] px-3 py-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap text-[var(--app-ink)]"
                >{{ active.detail }}</pre>
            </section>

            <section v-if="active.kind === 'thinking' && active.detail">
              <p class="app-label mb-1.5">{{ t('runs.chat.review.thinking') }}</p>
              <div
                class="rounded-xl border border-[var(--app-line)] bg-[var(--app-surface-2)] px-3 py-2.5 text-sm leading-relaxed whitespace-pre-wrap text-[var(--app-ink-soft)]"
              >
                {{ active.detail }}
              </div>
            </section>

            <section v-if="diffLines.length" class="flex min-h-0 flex-1 flex-col">
              <p class="app-label mb-1.5">{{ t('runs.chat.review.output') }}</p>
              <div
                class="code-diff min-h-[12rem] flex-1 overflow-auto rounded-xl border border-[var(--app-line)] bg-[var(--app-bg)]"
              >
                <div v-for="(row, i) in diffLines" :key="i" :class="['code-diff-line', `is-${row.type}`]">
                  <span class="code-diff-ln" aria-hidden="true">{{ row.lineNo ?? '' }}</span>
                  <span class="code-diff-text">{{ row.text || ' ' }}</span>
                </div>
              </div>
            </section>

            <p
              v-else-if="active.kind === 'edit' || active.kind === 'write'"
              class="rounded-xl border border-dashed border-[var(--app-line)] px-3 py-6 text-center text-sm text-[var(--app-ink-soft)]"
            >
              {{ t('runs.chat.review.noDiff') }}
            </p>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { ChatActionKind, ChatToolAction } from '~/utils/chatActions'
import { parseDiffLines, truncatePath } from '~/utils/chatActions'

/**
 * Bottom sheet (mobile) / modal (desktop) for reviewing file edits & tool actions.
 * List → detail navigation mirrors Claude Code mobile.
 */
const props = defineProps<{
  open: boolean
  kind: ChatActionKind
  actions: ChatToolAction[]
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const { t } = useI18n()

const view = ref<'list' | 'detail'>('list')
const detailIndex = ref(0)

const active = computed(() => props.actions[detailIndex.value] ?? null)
const diffLines = computed(() => parseDiffLines(active.value?.diff || ''))

const sheetTitle = computed(() => {
  if (view.value === 'detail') {
    if (active.value?.kind === 'bash') {
      return t('runs.chat.review.commandTitle')
    }
    if (active.value?.kind === 'thinking') {
      return t('runs.chat.review.thinking')
    }
    if (active.value?.kind === 'read') {
      return t('runs.chat.review.readTitle')
    }
    return t('runs.chat.review.editTitle')
  }
  switch (props.kind) {
    case 'edit':
    case 'write':
      return props.actions.length <= 1
        ? t('runs.chat.review.modifiedOne')
        : t('runs.chat.review.modifiedMany', { n: props.actions.length })
    case 'read':
      return props.actions.length <= 1
        ? t('runs.chat.review.readOne')
        : t('runs.chat.review.readMany', { n: props.actions.length })
    case 'bash':
      return props.actions.length <= 1
        ? t('runs.chat.review.ranOne')
        : t('runs.chat.review.ranMany', { n: props.actions.length })
    case 'thinking':
      return t('runs.chat.review.thinking')
    default:
      return t('runs.chat.review.action')
  }
})

/**
 * Icon for a tool action kind in the list timeline.
 */
function iconFor(kind: ChatActionKind): string {
  if (kind === 'read') return 'i-lucide-file-text'
  if (kind === 'bash') return 'i-lucide-terminal'
  if (kind === 'thinking') return 'i-lucide-clock'
  return 'i-lucide-pencil'
}

/**
 * Status word shown above the path (Modifié / Lu / …).
 */
function statusLabel(action: ChatToolAction): string {
  if (action.kind === 'read') return t('runs.chat.review.statusRead')
  if (action.kind === 'bash') return t('runs.chat.review.statusBash')
  if (action.kind === 'thinking') return t('runs.chat.review.statusThinking')
  if (action.kind === 'write') return t('runs.chat.review.statusWrite')
  return t('runs.chat.review.statusEdit')
}

/**
 * Open detail for one list item (auto-skip list when only one actionable item with diff).
 */
function openDetail(index: number): void {
  detailIndex.value = index
  view.value = 'detail'
}

/**
 * Close the sheet entirely.
 */
function close(): void {
  emit('update:open', false)
}

/**
 * Esc: back from detail, else close.
 */
function onEsc(): void {
  if (view.value === 'detail') {
    view.value = 'list'
    return
  }
  close()
}

/**
 * Lock body scroll while open.
 */
function setBodyLock(locked: boolean): void {
  if (typeof document === 'undefined') {
    return
  }
  document.body.style.overflow = locked ? 'hidden' : ''
}

watch(
  () => props.open,
  (isOpen) => {
    setBodyLock(isOpen)
    if (isOpen) {
      view.value = 'list'
      detailIndex.value = 0
      // Single file edit → jump straight to diff (faster on mobile).
      if (
        props.actions.length === 1 &&
        (props.actions[0]?.kind === 'edit' ||
          props.actions[0]?.kind === 'write' ||
          props.actions[0]?.kind === 'thinking' ||
          props.actions[0]?.kind === 'bash')
      ) {
        // Keep list for multi; for single edit still show list first like Claude
        // (user asked for list then detail). Stay on list.
        view.value = 'list'
      }
    }
  },
)

onBeforeUnmount(() => setBodyLock(false))
</script>

<style scoped>
.code-review-backdrop-enter-active,
.code-review-backdrop-leave-active {
  transition: opacity 0.22s ease;
}
.code-review-backdrop-enter-from,
.code-review-backdrop-leave-to {
  opacity: 0;
}

/* Animate the panel only — anchor stays flex-centered (no left/translate fight). */
.code-review-sheet-enter-active .code-review-panel,
.code-review-sheet-leave-active .code-review-panel {
  transition:
    transform 0.28s cubic-bezier(0.16, 1, 0.3, 1),
    opacity 0.22s ease;
}
.code-review-sheet-enter-active,
.code-review-sheet-leave-active {
  transition: opacity 0.22s ease;
}
.code-review-sheet-enter-from,
.code-review-sheet-leave-to {
  opacity: 1;
}
.code-review-sheet-enter-from .code-review-panel,
.code-review-sheet-leave-to .code-review-panel {
  opacity: 0;
  transform: translateY(100%);
}
@media (min-width: 640px) {
  .code-review-sheet-enter-from .code-review-panel,
  .code-review-sheet-leave-to .code-review-panel {
    transform: translateY(0.5rem) scale(0.98);
  }
}

@media (prefers-reduced-motion: reduce) {
  .code-review-backdrop-enter-active,
  .code-review-backdrop-leave-active,
  .code-review-sheet-enter-active,
  .code-review-sheet-leave-active,
  .code-review-sheet-enter-active .code-review-panel,
  .code-review-sheet-leave-active .code-review-panel {
    transition: none;
  }
}

.code-diff-line {
  display: flex;
  align-items: flex-start;
  font-family: var(--app-font-mono);
  font-size: 0.75rem;
  line-height: 1.55;
  min-height: 1.35rem;
}
.code-diff-ln {
  flex-shrink: 0;
  width: 2.75rem;
  padding: 0 0.5rem;
  text-align: right;
  user-select: none;
  color: var(--app-faint);
  border-right: 1px solid var(--app-line-soft);
}
.code-diff-text {
  flex: 1;
  min-width: 0;
  padding: 0 0.75rem;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--app-ink);
}
.code-diff-line.is-add {
  background: var(--app-green-soft);
}
.code-diff-line.is-add .code-diff-ln,
.code-diff-line.is-add .code-diff-text {
  color: var(--app-green);
}
.code-diff-line.is-del {
  background: var(--app-red-soft);
}
.code-diff-line.is-del .code-diff-ln,
.code-diff-line.is-del .code-diff-text {
  color: var(--app-red);
}
.code-diff-line.is-meta .code-diff-text,
.code-diff-line.is-skip .code-diff-text {
  color: var(--app-ink-soft);
}
.code-diff-line.is-skip .code-diff-ln {
  color: transparent;
}
</style>
