# Plan — Multi-comptes Cursor

## Objectif

Gérer plusieurs comptes Cursor dans NightForge : quotas (% + reset), coffre email/mot de passe chiffré, switch auto au prochain prompt (moyenne Auto+API la plus basse).

## Périmètre

1. **Page** `/dashboard/cursor-accounts` (bouton depuis la carte Utilisation).
2. **Épinglé en haut** : usage live « Machine actuelle » (session locale).
3. **Formulaire** : email + password (rappel) + **Se connecter avec Cursor**.
4. **Login** : **NoDriver** — Chrome isolé, cookie `WorkosCursorSessionToken`, **sans toucher** Cursor IDE.
5. **Avancé** : collage manuel token / API key (secours).
6. **Chiffrement Fernet** (`ENCRYPTION_KEY`).
7. **Drawer** : rappel email + password.
8. **Refresh** + **router** moyenne Auto+API au prochain prompt Cursor.

## Fichiers clés

- `api/services/encryption_service.py`, `api/models/cursor_account.py`, routes/schemas
- `agent/.../cursor_login.py` (NoDriver), `cursor_usage_reader.py`, `cursor_runner.py`
- `web/.../pages/dashboard/cursor-accounts.vue` + drawers + `CursorLogo.vue`
