/**
 * Lightweight Markdown → safe HTML for chat bubbles (bold, italic, code, links, lists).
 * Escapes HTML first so agent output cannot inject scripts.
 */

/**
 * Escape HTML special characters.
 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * Inline Markdown on an already-escaped string (no raw HTML allowed in).
 */
function renderInline(escaped: string): string {
  let out = escaped
  // `code`
  out = out.replace(/`([^`\n]+)`/g, '<code class="chat-md-code">$1</code>')
  // **bold** / __bold__
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  // *italic* / _italic_ (avoid matching inside words for _)
  out = out.replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>')
  out = out.replace(/(^|[\s(])_([^_\n]+)_(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>')
  // [label](https://...)
  out = out.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="chat-md-link">$1</a>',
  )
  return out
}

/**
 * Render a chat / log line (or multi-line block) to HTML.
 *
 * @param source - Raw Markdown text from the agent
 * @returns Sanitized HTML string
 */
export function renderChatMarkdown(source: string): string {
  if (!source) {
    return ''
  }

  const lines = source.replace(/\r\n/g, '\n').split('\n')
  const html: string[] = []
  let inCode = false
  let codeBuf: string[] = []
  let listBuf: string[] = []
  let listOrdered = false

  /**
   * Flush an open bullet/numbered list into ``html``.
   */
  function flushList(): void {
    if (!listBuf.length) {
      return
    }
    const tag = listOrdered ? 'ol' : 'ul'
    html.push(
      `<${tag} class="chat-md-list">${listBuf.map((item) => `<li>${renderInline(item)}</li>`).join('')}</${tag}>`,
    )
    listBuf = []
  }

  for (const rawLine of lines) {
    const fence = rawLine.match(/^```/)
    if (fence) {
      flushList()
      if (inCode) {
        html.push(`<pre class="chat-md-pre"><code>${codeBuf.join('\n')}</code></pre>`)
        codeBuf = []
        inCode = false
      } else {
        inCode = true
      }
      continue
    }

    if (inCode) {
      codeBuf.push(escapeHtml(rawLine))
      continue
    }

    const unordered = rawLine.match(/^[-*]\s+(.+)$/)
    if (unordered) {
      if (listBuf.length && listOrdered) {
        flushList()
      }
      listOrdered = false
      listBuf.push(escapeHtml(unordered[1] ?? ''))
      continue
    }

    const ordered = rawLine.match(/^\d+\.\s+(.+)$/)
    if (ordered) {
      if (listBuf.length && !listOrdered) {
        flushList()
      }
      listOrdered = true
      listBuf.push(escapeHtml(ordered[1] ?? ''))
      continue
    }

    flushList()

    if (!rawLine.trim()) {
      html.push('<br />')
      continue
    }

    // Markdown thematic break: --- / *** / ___ on their own line
    if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(rawLine.trim())) {
      html.push('<hr class="chat-md-hr" />')
      continue
    }

    const heading = rawLine.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      const level = heading[1]!.length
      html.push(`<p class="chat-md-h${level}"><strong>${renderInline(escapeHtml(heading[2] ?? ''))}</strong></p>`)
      continue
    }

    html.push(`<p class="chat-md-p">${renderInline(escapeHtml(rawLine))}</p>`)
  }

  if (inCode) {
    html.push(`<pre class="chat-md-pre"><code>${codeBuf.join('\n')}</code></pre>`)
  }
  flushList()

  return html.join('')
}
