# NightForge — Déploiement VPS & secrets GitHub

> À lire **avant** de pousser sur `main` pour déclencher les workflows CI/CD.

---

## 1. Sous-domaines à créer (DNS)

Oui, il te faut **deux sous-domaines** distincts (comme DevLeadHunter) :

| Sous-domaine | Rôle | Cible |
|---|---|---|
| `nightforge.dibodev.fr` | Application web (Nuxt SSR via PM2) | IP du VPS |
| `api.nightforge.dibodev.fr` | API FastAPI (Uvicorn via systemd) | IP du VPS |

Les workflows déploient déjà vers :
- API → `/var/www/api.nightforge.dibodev.fr/html`
- Web → `/var/www/nightforge.dibodev.fr/html` + `/var/www/nightforge.dibodev.fr/server`

Le workflow crée aussi un symlink `html → public` : Nitro résout les assets PWA depuis `../public/` (relatif à `server/`). Sans ce lien, `/apple-touch-icon.png` renvoie une erreur 500 et iOS affiche un « N » générique sur l’écran d’accueil.

---

## 2. Ports sur le VPS (écoute locale uniquement)

NGINX fait le reverse proxy public (443) → processus locaux. **Ne pas exposer ces ports sur Internet.**

> **Note VPS** : le port `8010` est déjà utilisé sur le VPS (autre service Uvicorn). NightForge écoute en prod sur **`8022`**. En dev local, l'API reste sur **`8010`** (voir §5).

| Service | Port local | Process manager | Coexistence DevLeadHunter |
|---|---|---|---|
| **NightForge API** | `8022` | `systemd` (`nightforge-api.service`) | DLH API = `8005`, `8010` déjà pris sur le VPS |
| **NightForge Web** | `5620` | `pm2` (`nightforge.dibodev.fr`) | DLH Web = `5615` |

### Exemple NGINX — API (`api.nightforge.dibodev.fr`)

```nginx
server {
    listen 443 ssl http2;
    server_name api.nightforge.dibodev.fr;

    # ssl_certificate ... (Let's Encrypt / certbot)

    location / {
        proxy_pass http://127.0.0.1:8022;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket (agents + dashboard live)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### Exemple NGINX — Web (`nightforge.dibodev.fr`)

```nginx
server {
    listen 443 ssl http2;
    server_name nightforge.dibodev.fr;

    # Fichiers statiques Nitro
    root /var/www/nightforge.dibodev.fr/html;
    index index.html;

    location /_nuxt/ {
        try_files $uri =404;
        access_log off;
        expires 30d;
    }

    # PWA / favicon — servis depuis html/ avant le proxy SSR (iOS Add to Home Screen)
    location ~ ^/(apple-touch-icon(-precomposed)?\.png|favicon\.ico|site\.webmanifest|android-chrome-.*\.png)$ {
        try_files $uri =404;
        access_log off;
        expires 30d;
    }

    location / {
        try_files $uri $uri/ @nitro;
    }

    location @nitro {
        proxy_pass http://127.0.0.1:5620;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 3. Base de données MariaDB (VPS)

Créer une base **dédiée** NightForge (ne pas réutiliser celle de DevLeadHunter) :

```sql
CREATE DATABASE nightforge CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'nightforge'@'localhost' IDENTIFIED BY 'TON_MOT_DE_PASSE_FORT';
GRANT ALL PRIVILEGES ON nightforge.* TO 'nightforge'@'localhost';
FLUSH PRIVILEGES;
```

`DATABASE_URL` pour le secret GitHub :

```
mysql+pymysql://nightforge:TON_MOT_DE_PASSE_FORT@127.0.0.1:3306/nightforge
```

Le workflow `deploy-api.yml` exécute `init_db.py` à chaque déploiement (schéma + seed admin).

---

## 4. Secrets GitHub à configurer

Dans **Settings → Secrets and variables → Actions** du repo `nightforge`.

### 4.1 Déploiement SSH (partagés API + Web)

| Secret | Description | Exemple |
|---|---|---|
| `SSH_HOST` | IP ou hostname du VPS | `xxx.xxx.xxx.xxx` |
| `SSH_PORT` | Port SSH | `22` |
| `SSH_USERNAME` | Utilisateur SSH de déploiement | `debian` ou ton user |
| `SSH_PRIVATE_KEY` | Clé privée SSH (contenu complet du `.pem`) | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

### 4.2 API (`deploy-api.yml`)

| Secret | Description | Exemple / génération |
|---|---|---|
| `API_BASE_URL` | URL publique de l'API | `https://api.nightforge.dibodev.fr` |
| `FRONTEND_URL` | URL publique du dashboard | `https://nightforge.dibodev.fr` |
| `CORS_ORIGINS` | Origines autorisées (virgules) | `https://nightforge.dibodev.fr,https://tauri.localhost,tauri://localhost` |
| `DATABASE_URL` | Connexion MariaDB | voir §3 |
| `SECRET_KEY` | Clé JWT (longue, aléatoire) | `openssl rand -hex 32` |
| `ADMIN_EMAIL` | Email admin initial (seeder) | `contact@dibodev.fr` |
| `ADMIN_PASSWORD` | Mot de passe admin initial | **mot de passe fort** (change-le après 1er login) |
| `ENCRYPTION_KEY` | Clé Fernet pour secrets agents | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GROQ_API_KEY` | Clé Groq (fallback Aide prompts IA si agent offline) | Console [console.groq.com](https://console.groq.com) |

### 4.3 Web (`deploy-web.yml`)

| Secret | Obligatoire | Description | Valeur recommandée |
|---|---|---|---|
| `NUXT_PUBLIC_API_BASE` | Non* | URL API compilée dans le front | `https://api.nightforge.dibodev.fr` |

\* Défaut dans le workflow et `nuxt.config.ts` si absent.

Les secrets SSH (§4.1) suffisent si tu gardes le défaut.

### 4.4 Desktop Tauri (`desktop-release.yml`)

> **Uniquement si tu veux publier l'app desktop Windows.** Pas nécessaire pour API/web.

Générer la paire de clés **une fois** (depuis `web/`) :

```powershell
# Windows — utiliser npx directement (npm intercepte -w sinon)
cd web
npx tauri signer generate -w "$env:USERPROFILE\.tauri\nightforge.key" -p "" --ci
```

Si les fichiers existent déjà : **ne pas régénérer**, réutilise-les. Pour forcer l'écrasement : ajouter `--force`.

Fichiers créés :

| Fichier | Rôle |
|---|---|
| `%USERPROFILE%\.tauri\nightforge.key` | Clé **privée** (secret GitHub) |
| `%USERPROFILE%\.tauri\nightforge.key.pub` | Clé **publique** (secret GitHub) |

Afficher le contenu à copier :

```powershell
Get-Content "$env:USERPROFILE\.tauri\nightforge.key.pub"   # → TAURI_UPDATER_PUBKEY
Get-Content "$env:USERPROFILE\.tauri\nightforge.key"       # → TAURI_SIGNING_PRIVATE_KEY
```

| Secret | Valeur à coller |
|---|---|
| `TAURI_UPDATER_PUBKEY` | Contenu entier de `nightforge.key.pub` (1 ligne base64) |
| `TAURI_SIGNING_PRIVATE_KEY` | Contenu entier de `nightforge.key` (1 ligne base64) |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | Vide (ne pas créer le secret, ou laisser vide) |
| `NUXT_PUBLIC_API_BASE` | `https://api.nightforge.dibodev.fr` (optionnel, défaut identique) |

`GITHUB_TOKEN` est fourni automatiquement par GitHub Actions.

---

## 5. Ports locaux (développement) — sans conflit DevLeadHunter

| Service | NightForge | DevLeadHunter |
|---|---|---|
| MariaDB | `3311` | `3310` |
| phpMyAdmin | `7501` | `7500` |
| API dev | `8010` | `8000` (typique) |
| Web dev | `3001`–`3003` (selon dispo) | `3000` (typique) |

### Démarrage local testé

```bash
# 1. Base de données
docker compose up -d

# 2. API (depuis la racine)
cp api/.env.example api/.env   # puis éditer
cd api && python init_db.py
python run_dev.py              # http://localhost:8010

# 3. Web
echo NUXT_PUBLIC_API_BASE=http://localhost:8010 > web/.env
cd web && npx nuxt dev --port 3001
```

Compte admin par défaut (seeder) : voir `ADMIN_EMAIL` / `ADMIN_PASSWORD` dans `api/.env`.

---

## 6. Checklist avant push sur `main`

- [ ] DNS `nightforge.dibodev.fr` + `api.nightforge.dibodev.fr` → VPS
- [ ] Base MariaDB `nightforge` créée sur le VPS
- [ ] Tous les secrets §4 renseignés dans GitHub
- [ ] Vhosts NGINX créés (§2) + certificats TLS
- [ ] Ports `8022` et `5620` libres sur le VPS (`8010` est déjà occupé sur ce VPS)
- [ ] Premier déploiement API → vérifier `https://api.nightforge.dibodev.fr/api/v1/health`
- [ ] Premier déploiement Web → vérifier login sur `https://nightforge.dibodev.fr`
- [ ] Enregistrer une machine dans le dashboard → copier le token agent dans l'app desktop

---

## 7. Résultats des tests locaux (2026-07-11)

| Test | Statut |
|---|---|
| Docker MariaDB (`3311`) + phpMyAdmin (`7501`) | OK |
| API health + DB | OK |
| Login JWT + `/auth/me` | OK |
| CRUD projets, file, messages composer | OK |
| Création machine + token agent | OK |
| Planificateur quotas | OK |
| Création run + snapshot `run_messages` | OK |
| UI login → dashboard → compose → projects | OK (CORS corrigé pour ports dev) |

L'agent Python et Tauri desktop n'ont pas été testés end-to-end ici (nécessitent Claude CLI + build Tauri sur ta machine).
