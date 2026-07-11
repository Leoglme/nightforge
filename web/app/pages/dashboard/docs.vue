<template>
  <div class="mx-auto flex max-w-2xl flex-col gap-6 pb-10">
    <header class="flex flex-col gap-2">
      <h1 class="app-page-title">Guide</h1>
      <p class="text-sm text-[var(--app-ink-soft)]">
        NightForge fait travailler Claude Code en autonomie pendant la nuit : tu composes une séquence de messages par
        projet, l'agent sur ton PC les exécute, gère le quota Claude Max et pousse le travail sur Git.
      </p>
    </header>

    <!-- How it works -->
    <section class="app-card p-5">
      <h2 class="mb-3 flex items-center gap-2 text-base font-semibold">
        <UIcon name="i-lucide-workflow" class="text-[var(--app-accent)]" />
        En 4 étapes
      </h2>
      <ol class="flex flex-col gap-3">
        <li v-for="(step, index) in flow" :key="index" class="flex gap-3">
          <span
            class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--app-accent-soft)] text-xs font-semibold text-[var(--app-accent-ink)]"
          >
            {{ index + 1 }}
          </span>
          <p class="text-sm text-[var(--app-ink-soft)]">
            <strong class="text-[var(--app-ink)]">{{ step.title }}</strong> — {{ step.body }}
          </p>
        </li>
      </ol>
    </section>

    <!-- Machine -->
    <section class="app-card p-5">
      <h2 class="mb-1 flex items-center gap-2 text-base font-semibold">
        <UIcon name="i-lucide-monitor-check" class="text-[var(--app-accent)]" />
        Ta machine
      </h2>
      <p class="mb-4 text-sm text-[var(--app-ink-soft)]">
        Depuis l'app desktop, ouvre
        <NuxtLink to="/dashboard/machines" class="text-[var(--app-accent-ink)] hover:underline">Machines</NuxtLink>
        et clique <strong>« Ajouter cette machine »</strong>. NightForge enregistre le PC et démarre l'agent tout seul —
        <strong>rien à installer ni à configurer</strong>.
      </p>
      <p class="flex items-start gap-2 text-sm text-[var(--app-ink-soft)]">
        <UIcon name="i-lucide-triangle-alert" class="mt-0.5 shrink-0 text-[var(--app-accent)]" />
        <span>
          Seul prérequis :
          <strong class="text-[var(--app-ink)]">Claude Code installé et connecté à ton compte Max</strong> sur ce PC
          (l'agent lance <code class="app-inline-code">claude</code> en local).
        </span>
      </p>
    </section>

    <!-- Projects & queue -->
    <section class="app-card p-5">
      <h2 class="mb-1 flex items-center gap-2 text-base font-semibold">
        <UIcon name="i-lucide-folder-git-2" class="text-[var(--app-accent)]" />
        Projets & idées
      </h2>
      <ul class="flex flex-col gap-2 text-sm text-[var(--app-ink-soft)]">
        <li class="flex gap-2">
          <UIcon name="i-lucide-check" class="mt-0.5 shrink-0 text-[var(--app-green)]" />
          <span>
            Un <strong class="text-[var(--app-ink)]">projet</strong> = un dépôt Git + le chemin où il est cloné sur ta
            machine. Tout se gère depuis le
            <NuxtLink to="/dashboard/compose" class="text-[var(--app-accent-ink)] hover:underline">Composer</NuxtLink>
            (bouton « + » et icône réglages).
          </span>
        </li>
        <li class="flex gap-2">
          <UIcon name="i-lucide-check" class="mt-0.5 shrink-0 text-[var(--app-green)]" />
          <span>
            La
            <NuxtLink to="/dashboard/queue" class="text-[var(--app-accent-ink)] hover:underline"
              >File d'attente</NuxtLink
            >
            garde tes idées de prompts réutilisables par projet. Tu les pioches ensuite pour composer un message.
          </span>
        </li>
      </ul>
    </section>

    <!-- Compose & launch -->
    <section class="app-card p-5">
      <h2 class="mb-1 flex items-center gap-2 text-base font-semibold">
        <UIcon name="i-lucide-messages-square" class="text-[var(--app-accent)]" />
        Composer & lancer
      </h2>
      <p class="mb-3 text-sm text-[var(--app-ink-soft)]">
        Le Composer est un chat : chaque message = un appel à Claude Code, exécuté dans l'ordre. Choisis la machine et
        le nombre de <strong class="text-[var(--app-ink)]">quotas</strong> (fenêtres de 5 h), puis lance.
      </p>
      <p class="text-sm text-[var(--app-ink-soft)]">
        Le quota est une fenêtre glissante de 5 h. Quand Claude atteint sa limite, l'agent lit l'heure de reset, attend,
        puis <strong class="text-[var(--app-ink)]">reprend automatiquement</strong>. Suis les logs en direct depuis les
        runs du tableau de bord.
      </p>
    </section>

    <div class="flex flex-wrap gap-3">
      <UButton to="/dashboard/compose" color="primary" icon="i-lucide-messages-square">Composer une nuit</UButton>
      <UButton to="/dashboard/queue" color="neutral" variant="outline" icon="i-lucide-lightbulb">
        Ajouter une idée
      </UButton>
    </div>
  </div>
</template>

<script lang="ts" setup>
/**
 * User documentation — a concise overview of how NightForge works.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const flow = [
  {
    title: 'Ajoute ta machine',
    body: "depuis l'app desktop, un clic sur « Ajouter cette machine » enregistre le PC et démarre l'agent.",
  },
  {
    title: 'Crée un projet',
    body: 'un dépôt Git + le chemin où il est cloné, dans le Composer.',
  },
  {
    title: 'Compose ta nuit',
    body: "écris (ou pioche dans la file d'attente) la séquence de messages pour Claude, comme un chat.",
  },
  {
    title: 'Lance & suis',
    body: "l'agent exécute message par message, gère le quota, commit et push ; tu suis les logs en direct.",
  },
]
</script>
