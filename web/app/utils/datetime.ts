/** Locale utilisée pour tout affichage date/heure dans l'app. */
export const APP_LOCALE = 'fr-FR' as const

const HAS_TZ = /[zZ]$|[+-]\d{2}:\d{2}$/

/**
 * Parse un timestamp API : les dates naïves sont en UTC (``datetime.utcnow()`` côté serveur).
 */
export function parseApiDateTime(value: string | Date): Date {
  if (value instanceof Date) {
    return value
  }
  return new Date(HAS_TZ.test(value) ? value : `${value}Z`)
}

const TIME_OPTS: Intl.DateTimeFormatOptions = {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
}

const CLOCK_OPTS: Intl.DateTimeFormatOptions = {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
}

const DATETIME_OPTS: Intl.DateTimeFormatOptions = {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
}

/**
 * Formate une date ISO en heure locale française (24 h), ex. « 04:50 ».
 */
export function formatTimeFr(value: string | Date): string {
  return parseApiDateTime(value).toLocaleTimeString(APP_LOCALE, TIME_OPTS)
}

/**
 * Formate une date ISO en date + heure françaises, ex. « 11/07/2026 04:50 ».
 */
export function formatDateTimeFr(value: string | Date): string {
  return parseApiDateTime(value).toLocaleString(APP_LOCALE, DATETIME_OPTS)
}

/**
 * Formate une date ISO en horloge avec secondes (logs live).
 */
export function formatClockFr(value: string | Date): string {
  return parseApiDateTime(value).toLocaleTimeString(APP_LOCALE, CLOCK_OPTS)
}

/**
 * Heure du jour, ou « sam. 04:50 » si ce n'est pas aujourd'hui.
 */
export function formatTimeLabelFr(iso: string): string {
  const d = parseApiDateTime(iso)
  const time = formatTimeFr(d)
  if (d.toDateString() === new Date().toDateString()) {
    return time
  }
  const day = d.toLocaleDateString(APP_LOCALE, { weekday: 'short' })
  return `${day} ${time}`
}
