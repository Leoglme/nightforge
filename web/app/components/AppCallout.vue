<template>
  <div :class="['app-callout', `app-callout--${variant}`]" role="note">
    <UIcon :name="icon ?? tokens.icon" class="app-callout__icon" aria-hidden="true" />
    <div class="app-callout__body">
      <slot />
    </div>
  </div>
</template>

<script lang="ts" setup>
import type { ComputedRef, PropType } from 'vue'
import { computed } from 'vue'
import type { UiCalloutProps, UiCalloutVariant } from '~/types/uiCallout'

/** Resolved icon + variant key for a callout. */
interface CalloutTokens {
  icon: string
}

/**
 * Defines the component props.
 */
const props: UiCalloutProps = defineProps({
  variant: {
    type: String as PropType<UiCalloutVariant>,
    default: 'info',
  },
  icon: {
    type: String,
    default: undefined,
  },
})

/** Per-variant default icons. */
const ICONS: Record<UiCalloutVariant, string> = {
  info: 'i-lucide-info',
  warning: 'i-lucide-triangle-alert',
  success: 'i-lucide-circle-check',
  neutral: 'i-lucide-info',
}

/** Resolved tokens for the current variant. */
const tokens: ComputedRef<CalloutTokens> = computed((): CalloutTokens => ({
  icon: ICONS[props.variant ?? 'info'],
}))
</script>
