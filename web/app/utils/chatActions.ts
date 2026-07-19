/**
 * Parse NightForge structured tool actions (`__NF_ACTION__:…`) from run events
 * and build a Claude-Code-style chat timeline (text + tappable action groups).
 */

export const NF_ACTION_PREFIX = '__NF_ACTION__:'

export type ChatActionKind = 'edit' | 'write' | 'read' | 'bash' | 'thinking'

export interface ChatToolAction {
  kind: ChatActionKind
  path?: string
  additions?: number
  deletions?: number
  /** Unified / line-oriented diff text */
  diff?: string
  /** Bash command or thinking snippet */
  detail?: string
}

export type ChatTimelineItem =
  | { type: 'text'; id: string; message: string; level: string }
  | { type: 'action-group'; id: string; kind: ChatActionKind; actions: ChatToolAction[] }

/**
 * Try to parse a single event message as a structured tool action.
 */
export function parseChatAction(message: string): ChatToolAction | null {
  if (!message.startsWith(NF_ACTION_PREFIX)) {
    return null
  }
  try {
    const raw = JSON.parse(message.slice(NF_ACTION_PREFIX.length)) as Record<string, unknown>
    const kind = String(raw.kind || '')
    if (!['edit', 'write', 'read', 'bash', 'thinking'].includes(kind)) {
      return null
    }
    return {
      kind: kind as ChatActionKind,
      path: typeof raw.path === 'string' ? raw.path : undefined,
      additions: typeof raw.additions === 'number' ? raw.additions : 0,
      deletions: typeof raw.deletions === 'number' ? raw.deletions : 0,
      diff: typeof raw.diff === 'string' ? raw.diff : undefined,
      detail: typeof raw.detail === 'string' ? raw.detail : undefined,
    }
  } catch {
    return null
  }
}

/**
 * Whether text looks like a unified / git diff.
 */
function looksLikeUnifiedDiff(text: string): boolean {
  const head = text.trimStart().slice(0, 800)
  return (
    head.includes('diff --git ') ||
    head.startsWith('--- ') ||
    head.includes('\n--- ') ||
    head.startsWith('+++ ') ||
    head.includes('@@ ')
  )
}

/**
 * Count +/- lines in a unified diff body.
 */
function countDiffStats(diffBody: string): { additions: number; deletions: number } {
  let additions = 0
  let deletions = 0
  for (const line of diffBody.split('\n')) {
    if (line.startsWith('+') && !line.startsWith('+++')) additions += 1
    else if (line.startsWith('-') && !line.startsWith('---')) deletions += 1
  }
  return { additions, deletions }
}

/**
 * Split a multi-file unified diff into per-file edit actions.
 */
export function actionsFromUnifiedDiff(diffText: string): ChatToolAction[] {
  if (!looksLikeUnifiedDiff(diffText)) {
    return []
  }
  const lines = diffText.replace(/\r\n/g, '\n').split('\n')
  const chunks: Array<{ path: string; body: string[] }> = []
  let currentPath = ''
  let current: string[] = []

  /**
   * Push the current file chunk.
   */
  function flush(): void {
    const body = current
    let path = currentPath
    currentPath = ''
    current = []
    if (!body.length) {
      return
    }
    if (!path) {
      for (const row of body) {
        if (row.startsWith('+++ b/')) {
          path = row.slice(6).trim()
          break
        }
        if (row.startsWith('+++ ') && !row.includes('/dev/null')) {
          path = row.slice(4).trim().replace(/^b\//, '')
          break
        }
      }
    }
    if (path === '/dev/null') {
      path = ''
    }
    if (path || body.some((r) => r.startsWith('+') || r.startsWith('-') || r.startsWith('@@'))) {
      chunks.push({ path: path || 'file', body })
    }
  }

  for (const line of lines) {
    if (line.startsWith('diff --git ')) {
      flush()
      const parts = line.split(/\s+/)
      let path = parts[3] || ''
      if (path.startsWith('b/')) {
        path = path.slice(2)
      }
      currentPath = path
      current = [line]
      continue
    }
    if (!current.length && (line.startsWith('--- ') || line.startsWith('+++ '))) {
      current = [line]
      continue
    }
    if (current.length) {
      current.push(line)
    }
  }
  flush()

  return chunks.map(({ path, body }) => {
    const diff = body.join('\n')
    const { additions, deletions } = countDiffStats(diff)
    return { kind: 'edit' as const, path, additions, deletions, diff }
  })
}

/**
 * Pull markdown ```diff fences (and whole-message git diffs) into review actions.
 */
function extractMarkdownDiffs(message: string): { text: string; actions: ChatToolAction[] } {
  const actions: ChatToolAction[] = []
  let text = message

  // Whole message is a raw git diff (no fence).
  if (looksLikeUnifiedDiff(message) && message.includes('diff --git ')) {
    const parsed = actionsFromUnifiedDiff(message)
    if (parsed.length) {
      return { text: '', actions: parsed }
    }
  }

  const fenceRe = /```(?:diff|patch|udiff)?\r?\n([\s\S]*?)```/gi
  const matches = [...message.matchAll(fenceRe)]
  for (const match of matches) {
    const body = match[1] || ''
    if (!looksLikeUnifiedDiff(body)) {
      continue
    }
    const parsed = actionsFromUnifiedDiff(body)
    if (parsed.length) {
      actions.push(...parsed)
      text = text.replace(match[0], '')
    }
  }
  // Collapse leftover blank lines from removed fences.
  text = text.replace(/\n{3,}/g, '\n\n').trim()
  return { text, actions }
}

/**
 * Agent noise that should not appear in the chat bubble.
 */
function isAgentNoise(message: string): boolean {
  const trimmed = message.trim()
  // Do NOT filter __NF_ACTION__ here — those become review rows via parseChatAction.
  return trimmed === 'Quota hit — waiting for reset' || trimmed.startsWith('__NF_RESULT__:')
}

/**
 * Whether two consecutive actions should collapse into one chat row.
 */
function sameGroup(a: ChatActionKind, b: ChatActionKind): boolean {
  const fileLike = (k: ChatActionKind) => k === 'edit' || k === 'write'
  if (fileLike(a) && fileLike(b)) {
    return true
  }
  return a === b && (a === 'bash' || a === 'thinking' || a === 'read')
}

/**
 * Build the interleaved text / action timeline for one assistant turn.
 */
export function buildChatTimeline(events: Array<{ id: number; level: string; message: string }>): ChatTimelineItem[] {
  const items: ChatTimelineItem[] = []
  let pending: ChatToolAction[] = []
  let pendingKind: ChatActionKind | null = null
  let pendingId = ''

  /**
   * Flush consecutive tool actions into one timeline row.
   */
  function flushActions(): void {
    if (!pending.length || !pendingKind) {
      return
    }
    items.push({
      type: 'action-group',
      id: pendingId,
      kind: pendingKind === 'write' ? 'edit' : pendingKind,
      actions: pending,
    })
    pending = []
    pendingKind = null
    pendingId = ''
  }

  /**
   * Append one or more actions into the pending group.
   */
  function pushActions(evId: number, list: ChatToolAction[]): void {
    for (const action of list) {
      const groupKind: ChatActionKind = action.kind === 'write' ? 'edit' : action.kind
      if (pendingKind && !sameGroup(pendingKind, groupKind)) {
        flushActions()
      }
      if (!pendingKind) {
        pendingKind = groupKind
        pendingId = `action-${evId}`
      }
      pending.push(action)
    }
  }

  for (const ev of events) {
    if (isAgentNoise(ev.message)) {
      continue
    }
    const action = parseChatAction(ev.message)
    if (action) {
      pushActions(ev.id, [action])
      continue
    }
    // Plain text may embed ```diff fences — lift them into review rows.
    const { text, actions: embedded } = extractMarkdownDiffs(ev.message)
    if (embedded.length) {
      pushActions(ev.id, embedded)
    }
    if (!text.trim()) {
      continue
    }
    flushActions()
    items.push({
      type: 'text',
      id: `text-${ev.id}`,
      message: text,
      level: ev.level,
    })
  }
  flushActions()
  return items
}

/**
 * Aggregate +/− across a group of file edits.
 */
export function sumDiffStats(actions: ChatToolAction[]): { additions: number; deletions: number } {
  return actions.reduce(
    (acc, a) => ({
      additions: acc.additions + (a.additions || 0),
      deletions: acc.deletions + (a.deletions || 0),
    }),
    { additions: 0, deletions: 0 },
  )
}

/**
 * Shorten a file path for mobile rows (keep start drive/root + filename).
 */
export function truncatePath(path: string, max = 42): string {
  if (!path || path.length <= max) {
    return path
  }
  const sep = path.includes('\\') ? '\\' : '/'
  const parts = path.split(sep).filter(Boolean)
  const file = parts[parts.length - 1] || path
  if (file.length >= max - 3) {
    return `…${file.slice(-(max - 1))}`
  }
  const head = parts[0] || ''
  const budget = max - file.length - 4
  const headKeep = head.slice(0, Math.max(budget, 4))
  return `${headKeep}…${sep}${file}`
}

export interface DiffLine {
  type: 'add' | 'del' | 'ctx' | 'meta' | 'skip'
  text: string
  /** Display line number when available */
  lineNo?: number
}

/**
 * Parse a unified diff string into display rows (with optional context collapse).
 */
export function parseDiffLines(diff: string): DiffLine[] {
  if (!diff) {
    return []
  }
  const rows: DiffLine[] = []
  let oldNo = 0
  let newNo = 0

  for (const raw of diff.replace(/\r\n/g, '\n').split('\n')) {
    if (!raw && rows.length === 0) {
      continue
    }
    if (raw.startsWith('@@')) {
      const m = raw.match(/@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)/)
      if (m) {
        oldNo = Number(m[1]) - 1
        newNo = Number(m[2]) - 1
      }
      rows.push({ type: 'meta', text: raw })
      continue
    }
    if (raw.startsWith('+++') || raw.startsWith('---') || raw.startsWith('diff ')) {
      rows.push({ type: 'meta', text: raw })
      continue
    }
    if (raw.startsWith('+')) {
      newNo += 1
      rows.push({ type: 'add', text: raw.slice(1), lineNo: newNo })
      continue
    }
    if (raw.startsWith('-')) {
      oldNo += 1
      rows.push({ type: 'del', text: raw.slice(1), lineNo: oldNo })
      continue
    }
    if (raw.startsWith(' ') || raw === '') {
      oldNo += 1
      newNo += 1
      rows.push({ type: 'ctx', text: raw.startsWith(' ') ? raw.slice(1) : raw, lineNo: newNo })
      continue
    }
    if (raw.startsWith('…') || raw === '...') {
      rows.push({ type: 'skip', text: '…' })
      continue
    }
    rows.push({ type: 'ctx', text: raw })
  }

  return collapseContext(rows)
}

/**
 * Collapse long unchanged runs to a single ellipsis (Claude mobile style).
 */
function collapseContext(rows: DiffLine[], keep = 2): DiffLine[] {
  const out: DiffLine[] = []
  let ctxBuf: DiffLine[] = []

  /**
   * Flush buffered context lines, collapsing the middle when long.
   */
  function flushCtx(): void {
    if (ctxBuf.length <= keep * 2 + 1) {
      out.push(...ctxBuf)
    } else {
      out.push(...ctxBuf.slice(0, keep))
      out.push({ type: 'skip', text: '…' })
      out.push(...ctxBuf.slice(-keep))
    }
    ctxBuf = []
  }

  for (const row of rows) {
    if (row.type === 'ctx') {
      ctxBuf.push(row)
      continue
    }
    flushCtx()
    out.push(row)
  }
  flushCtx()
  return out
}
