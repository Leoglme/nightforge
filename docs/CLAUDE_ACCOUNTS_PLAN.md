# Plan — Multi-comptes Claude

## Objectif

Gérer plusieurs comptes Claude Max : quotas (5 h / hebdo / Opus), coffre email/mot de passe, switch auto au prochain prompt.

## Périmètre (miroir Cursor)

1. Page `/dashboard/claude-accounts` (bouton depuis Utilisation → Claude Max).
2. Épinglé : session machine locale (`~/.claude`).
3. Coffre : autres comptes uniquement (pas de doublon machine).
4. Login : `claude auth login` (backup → login → capture OAuth → restore).
5. Avancé : collage JSON OAuth.
6. Switch : `CLAUDE_CODE_OAUTH_TOKEN` au prochain prompt Claude.

## Accès

Dashboard → Claude Max → **Tous les comptes**
