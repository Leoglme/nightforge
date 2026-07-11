export default defineAppConfig({
  ui: {
    colors: {
      primary: 'neutral',
      neutral: 'zinc',
    },
    button: {
      slots: {
        base: 'inline-flex items-center justify-center gap-2 font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50',
      },
      variants: {
        size: {
          md: { base: 'h-10 px-4 text-sm' },
          lg: { base: 'h-12 px-6 text-base' },
        },
      },
      compoundVariants: [
        {
          color: 'primary',
          variant: 'solid',
          class:
            'rounded-full bg-[var(--app-btn-bg)] text-[var(--app-btn-text)] shadow-sm hover:opacity-90 hover:shadow-md',
        },
        {
          color: 'neutral',
          variant: 'outline',
          class:
            'rounded-full border border-[var(--app-line)] bg-transparent text-[var(--app-ink)] hover:border-[var(--app-ink-soft)] hover:bg-[var(--app-surface-2)]',
        },
        {
          color: 'error',
          variant: 'solid',
          class: 'rounded-full bg-[var(--app-red)] text-[var(--app-surface)] hover:opacity-90',
        },
      ],
      defaultVariants: {
        size: 'md',
      },
    },
    input: {
      slots: {
        root: 'w-full',
        base: 'h-9 w-full rounded-lg px-3 text-sm transition-all',
      },
    },
    textarea: {
      slots: {
        root: 'w-full',
        base: 'w-full rounded-lg px-3 py-2 text-sm transition-all',
      },
    },
    card: {
      slots: {
        root: 'rounded-xl border border-[var(--app-line)] bg-[var(--app-surface)] shadow-none',
        header: 'border-b border-[var(--app-line)]',
        body: 'text-[var(--app-ink)]',
        footer: 'border-t border-[var(--app-line)]',
      },
    },
    formField: {
      slots: {
        label: 'text-xs font-medium text-[var(--app-ink-soft)]',
        error: 'text-xs text-[var(--app-red)]',
        hint: 'text-xs text-[var(--app-ink-soft)]',
      },
    },
    badge: {
      slots: {
        base: 'rounded-full px-2 py-0.5 text-xs font-medium',
      },
    },
  },
})
