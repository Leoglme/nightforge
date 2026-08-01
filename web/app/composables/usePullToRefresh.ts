import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'

/** Options for {@link usePullToRefresh}. */
export type PullToRefreshOptions = {
  /** Called when the pull passes the threshold (usually reloads the app). */
  onRefresh: () => void | Promise<void>
  /** Disable the gesture (e.g. on full-bleed chat pages). */
  enabled?: () => boolean
  /** Pixels to pull before a refresh triggers. */
  threshold?: number
}

/**
 * Touch pull-to-refresh for a scroll container — an iOS home-screen PWA has no native one.
 * @param target - The scrollable element to watch.
 * @param options - Refresh callback, enable guard and threshold.
 * @returns Reactive `pullDistance` (px) and `refreshing` for the indicator.
 */
export function usePullToRefresh(
  target: Ref<HTMLElement | null>,
  options: PullToRefreshOptions,
): { pullDistance: Ref<number>; refreshing: Ref<boolean> } {
  const threshold = options.threshold ?? 72
  const pullDistance = ref(0)
  const refreshing = ref(false)
  let startY = 0
  let tracking = false

  /**
   * Begin tracking only when the container is scrolled to the very top.
   * @param event - The touchstart event.
   * @returns Nothing.
   */
  function onTouchStart(event: TouchEvent): void {
    const el = target.value
    const allowed = options.enabled ? options.enabled() : true
    if (!el || refreshing.value || !allowed || el.scrollTop > 0) {
      return
    }
    startY = event.touches[0]?.clientY ?? 0
    tracking = true
  }

  /**
   * Follow the finger with a resistance curve while pulling down at the top.
   * @param event - The touchmove event.
   * @returns Nothing.
   */
  function onTouchMove(event: TouchEvent): void {
    const el = target.value
    if (!tracking || refreshing.value || !el) {
      return
    }
    const delta = (event.touches[0]?.clientY ?? 0) - startY
    if (delta <= 0 || el.scrollTop > 0) {
      pullDistance.value = 0
      return
    }
    pullDistance.value = Math.min(delta * 0.5, threshold * 1.6)
    if (pullDistance.value > 4) {
      event.preventDefault()
    }
  }

  /**
   * Trigger the refresh if pulled far enough, else snap back.
   * @returns Nothing.
   */
  async function onTouchEnd(): Promise<void> {
    if (!tracking) {
      return
    }
    tracking = false
    if (pullDistance.value < threshold || refreshing.value) {
      pullDistance.value = 0
      return
    }
    refreshing.value = true
    pullDistance.value = threshold
    try {
      await options.onRefresh()
    } finally {
      refreshing.value = false
      pullDistance.value = 0
    }
  }

  /**
   * Bind the touch listeners on an element.
   * @param el - The scroll container.
   * @returns Nothing.
   */
  function attach(el: HTMLElement): void {
    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: false })
    el.addEventListener('touchend', onTouchEnd, { passive: true })
    el.addEventListener('touchcancel', onTouchEnd, { passive: true })
  }

  /**
   * Remove the touch listeners from an element.
   * @param el - The scroll container.
   * @returns Nothing.
   */
  function detach(el: HTMLElement): void {
    el.removeEventListener('touchstart', onTouchStart)
    el.removeEventListener('touchmove', onTouchMove)
    el.removeEventListener('touchend', onTouchEnd)
    el.removeEventListener('touchcancel', onTouchEnd)
  }

  onMounted(() => {
    if (target.value) {
      attach(target.value)
    }
  })

  watch(target, (element, previous) => {
    if (previous) {
      detach(previous)
    }
    if (element) {
      attach(element)
    }
  })

  onBeforeUnmount(() => {
    if (target.value) {
      detach(target.value)
    }
  })

  return { pullDistance, refreshing }
}
