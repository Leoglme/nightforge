# Standards de code & architecture — NightForge

> Conventions reprises de DevLeadHunter pour garder une base cohérente.

## Monorepo

```
nightforge/
  api/     # FastAPI + MariaDB (control-plane, sur le VPS)
  web/     # Nuxt 4 + Tauri 2 (UI web + desktop)
  agent/   # Agent Python (sur chaque PC — lance Claude Code, sidecar Tauri)
```

Voir [`ARCHITECTURE.md`](./ARCHITECTURE.md) pour la conception complète.

## Backend (`api/`)

- **FastAPI + Pydantic v2 + SQLAlchemy 2 (Mapped/mapped_column) + MariaDB** (`pymysql`).
- Arborescence : `core/` (config, database), `models/` (ORM), `schemas/` (Pydantic),
  `enums/`, `services/`, `api/v1/routes/`, `seeders/`.
- Config via `pydantic-settings` (`core/config.py`), variables d'env avec alias MAJUSCULE.
- Auth JWT (bcrypt + python-jose), dépendances `get_current_active_user` / `require_admin`.
- Workers en boucle `async while True` + tick, lancés via `asyncio.create_task` au startup
  (pattern `email_queue_worker` de DevLeadHunter).
- Toutes les ressources scopées par `user_id`.
- Docstrings sur fonctions/méthodes.

## Frontend (`web/`)

- **Nuxt 4, Vue 3.5, TypeScript strict, Pinia, Nuxt UI v4, Tailwind v4, i18n** (en/fr).
- `ssr: false` en build desktop (`NUXT_DESKTOP_BUILD=1`), preset `static`.
- Services HTTP dans `app/services/`, stores Pinia dans `app/stores/`, composables dans
  `app/composables/`, types dans `app/types/`.
- Thème via tokens `--app-*` (light/dark) dans `assets/css/main.css`, remappés sur `--ui-*`.
- Icônes **lucide** (`@iconify-json/lucide`).
- Lint : `npm --prefix web run lint` (prettier + eslint + vue-tsc). Prettier : pas de `;`,
  quotes simples, `printWidth: 120`.

## Desktop (`web/src-tauri/`)

- **Tauri 2**, auto-updater signé (minisign), CI Windows.
- L'app lance l'**agent Python** en **sidecar** au démarrage (voir `agent/`).

## Agent (`agent/`)

- **Python** : WebSocket sortant vers le control-plane, spawn `claude` / Cursor `agent`
  (subprocess), git, lecture quota. Packagé en binaire (PyInstaller) et embarqué comme
  sidecar Tauri.

## Documentation

- **Mettre à jour les README dès qu’une feature change** (comportement UI, env, ports,
  providers, modes de run, lifecycle agent). Le README racine est la source « comment
  utiliser / installer » ; le détail design reste dans `docs/ARCHITECTURE.md`.
- Pas de guide in-app : l’installation et le setup machine sont dans le README + le
  modal Machines (étapes `.env` / token).

## Git & commits

- Conventional commits (`commitlint.json`) : `feat`, `fix`, `ci`, `docs`, `style`,
  `refactor`, `test`, `chore`, `perf`, `revert`, `build`.
- Hooks husky : `pre-commit` (lint), `commit-msg` (commitlint).
