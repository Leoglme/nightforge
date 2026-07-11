<template>
  <UApp :locale="uiLocale">
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>

<script lang="ts" setup>
import { fr } from '@nuxt/ui/locale'

/**
 * Root application shell. Auth is initialized in the auth.client plugin.
 * UApp locale = libellés Nuxt UI (sélecteurs, recherche…) + format heure 24 h.
 */
const uiLocale = fr
</script>
