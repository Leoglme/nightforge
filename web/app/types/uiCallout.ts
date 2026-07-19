/** Semantic variant of a callout annotation. */
export type UiCalloutVariant = 'info' | 'warning' | 'success' | 'neutral'

/**
 * Props of the AppCallout component.
 */
export interface UiCalloutProps {
  /** Semantic colour family. */
  variant?: UiCalloutVariant
  /** Override the default lucide icon of the variant. */
  icon?: string
}
