<template>
  <aside
    class="flex w-full shrink-0 flex-col border-b border-[var(--app-line)] bg-[var(--app-surface)] lg:w-52 lg:border-r lg:border-b-0"
  >
    <!-- Desktop header -->
    <div class="hidden items-center justify-between px-3 py-3 lg:flex">
      <span class="app-label">Projets</span>
      <UButton size="xs" color="neutral" variant="ghost" icon="i-lucide-plus" @click="emit('add')" />
    </div>

    <div v-if="projects.length === 0" class="hidden px-3 pb-4 text-xs text-[var(--app-ink-soft)] lg:block">
      Aucun projet sélectionné.
    </div>

    <!-- Pills (horizontal, mobile) / vertical list (desktop) -->
    <div class="flex items-center gap-1 px-2 py-1.5 lg:block lg:px-1 lg:py-0 lg:pb-2">
      <ul class="flex min-w-0 flex-1 gap-1 overflow-x-auto lg:flex-col lg:gap-0.5 lg:overflow-x-visible">
        <li v-for="project in projects" :key="project.id" class="shrink-0 lg:shrink">
          <button
            type="button"
            :class="[
              'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors',
              project.id === activeId
                ? 'bg-[var(--app-accent-soft)] text-[var(--app-ink)]'
                : 'text-[var(--app-ink-soft)] hover:bg-[var(--app-surface-2)] hover:text-[var(--app-ink)]',
            ]"
            @click="emit('select', project.id)"
          >
            <UIcon name="i-lucide-folder-git-2" class="shrink-0 text-[var(--app-accent)]" />
            <span class="min-w-0 flex-1 truncate">{{ project.name }}</span>
            <span class="rounded-full bg-[var(--app-surface-2)] px-1.5 text-[0.65rem] text-[var(--app-ink-soft)]">
              {{ messageCount(project.id) }}
            </span>
          </button>
        </li>
      </ul>

      <!-- Mobile add button -->
      <UButton
        size="sm"
        color="neutral"
        variant="outline"
        icon="i-lucide-plus"
        class="shrink-0 lg:hidden"
        aria-label="Ajouter un projet"
        @click="emit('add')"
      />
    </div>
  </aside>
</template>

<script lang="ts" setup>
import type { Project } from '~/types'

/**
 * Left sidebar listing projects selected for the night composer.
 */
defineProps<{
  projects: Project[]
  activeId: number
  messageCount: (projectId: number) => number
}>()

const emit = defineEmits<{
  select: [projectId: number]
  add: []
}>()
</script>
