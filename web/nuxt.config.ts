// https://nuxt.com/docs/api/configuration/nuxt-config
import { defineNuxtConfig } from 'nuxt/config'

const isDesktopBuild: boolean = process.env.NUXT_DESKTOP_BUILD === '1'

export default defineNuxtConfig({
  modules: ['@nuxt/eslint', '@nuxt/ui', '@vueuse/nuxt', '@pinia/nuxt', '@nuxtjs/i18n'],

  ssr: !isDesktopBuild,

  devtools: { enabled: !isDesktopBuild },

  app: {
    head: {
      title: 'NightForge — Claude Code autonome la nuit',
      htmlAttrs: { lang: 'fr' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        {
          name: 'description',
          content:
            'NightForge pilote Claude Code en autonomie pendant la nuit : files de prompts par projet, gestion du quota Claude Max, runs multi-machines, contrôle web et desktop.',
        },
        { name: 'theme-color', content: '#131312' },
      ],
      link: [
        { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
        { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' },
        {
          rel: 'stylesheet',
          href: 'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap',
        },
      ],
    },
  },

  css: ['~/assets/css/main.css'],

  colorMode: {
    preference: 'dark',
    fallback: 'dark',
    classSuffix: '',
  },

  ui: {
    fonts: false,
    theme: {
      colors: ['primary', 'neutral', 'success', 'info', 'warning', 'error'],
    },
  },

  runtimeConfig: {
    public: {
      apiBase:
        process.env.NUXT_PUBLIC_API_BASE ||
        (process.env.NODE_ENV === 'production' ? 'https://api.nightforge.dibodev.fr' : 'http://localhost:8010'),
      githubRepo: process.env.NUXT_PUBLIC_GITHUB_REPO || 'dibodev/nightforge',
      isDesktop: isDesktopBuild,
    },
  },

  compatibilityDate: '2024-07-11',

  nitro: isDesktopBuild ? { preset: 'static' } : undefined,

  typescript: {
    strict: true,
    typeCheck: false,
  },

  eslint: {
    config: {
      stylistic: {
        commaDangle: 'only-multiline',
        braceStyle: '1tbs',
      },
    },
  },

  i18n: {
    locales: [{ code: 'fr', language: 'fr-FR', name: 'Français', file: 'fr.json' }],
    defaultLocale: 'fr',
    strategy: 'no_prefix',
    langDir: 'locales',
    vueI18n: 'i18n.config.ts',
    detectBrowserLanguage: false,
  },
})
