/**
 * Copy Tauri iOS/desktop icons into `public/` for PWA / Add to Home Screen.
 * iOS expects a 180×180 `apple-touch-icon.png` at the site root.
 */
import { copyFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const ios180 = join(root, 'src-tauri/icons/ios/AppIcon-60x60@3x.png')
const publicDir = join(root, 'public')

if (!existsSync(ios180)) {
  console.error('Missing iOS 180px icon — run: npm run desktop:icons')
  process.exit(1)
}

for (const name of ['apple-touch-icon.png', 'apple-touch-icon-precomposed.png']) {
  copyFileSync(ios180, join(publicDir, name))
  console.log(`Wrote public/${name} (180×180)`)
}

const icon512 = join(root, 'src-tauri/icons/icon.png')
if (existsSync(icon512)) {
  copyFileSync(icon512, join(publicDir, 'android-chrome-512x512.png'))
  console.log('Wrote public/android-chrome-512x512.png')
}

const icon192 = join(root, 'src-tauri/icons/128x128@2x.png')
if (existsSync(icon192)) {
  copyFileSync(icon192, join(publicDir, 'android-chrome-192x192.png'))
  console.log('Wrote public/android-chrome-192x192.png')
}

const favicon = join(root, 'src-tauri/icons/icon.ico')
if (existsSync(favicon)) {
  copyFileSync(favicon, join(publicDir, 'favicon.ico'))
  console.log('Wrote public/favicon.ico')
}
