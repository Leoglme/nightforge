# NightForge V2 — Checklist de suivi

> Miroir du plan d’implémentation. Cocher au fil de l’avancement.

## Décisions figées

- Agent = durée de vie de l’app Tauri uniquement (pas de service / autostart Windows).
- Cursor autonome via CLI `agent -p --force --trust --approve-mcps`.
- Métadonnées provider/model/effort/fast sur `queue_items` puis Composer / runs.
- Runs mixtes Claude + Cursor autorisés (par message).
- Defaults : Sonnet→max, Opus→high, Fable→xhigh, Grok 4.5→high, Composer 2.5→pas d’effort / fast off.

## Phases

- [x] **Phase 0** — Ce fichier de suivi
- [x] **Phase 1** — Lifecycle sidecar + ticks idle
- [x] **Phase 2** — Schéma provider/model/effort/fast + presets
- [x] **Phase 3** — UI File d’attente + Composer multi-provider
- [x] **Phase 4** — `cursor_runner` + dispatch agent/API
- [x] **Phase 5** — README + ARCHITECTURE
- [x] **Phase 6** — Multi-comptes Cursor (coffre chiffré + page + switch au prochain prompt)
- [x] **Phase 7** — Multi-comptes Claude (coffre OAuth + page + switch au prochain prompt)

## Hors scope V2

- Service Windows / Task Scheduler / wake-from-sleep
- Pilotage GUI de l’IDE Cursor
- Quota planner Cursor
- `agent login` CLI / lecture du navigateur système (capture = NoDriver isolé + Avancé manuel)
