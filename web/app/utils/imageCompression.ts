import type { ComposerImage } from '~/types'

/**
 * Client-side image compression for chat attachments.
 * @module utils/imageCompression
 */

/** Longest-edge cap (px) — matches Claude's recommended input resolution. */
const MAX_DIMENSION = 1568

/** JPEG quality for the re-encoded attachment. */
const JPEG_QUALITY = 0.85

/**
 * Load a File into an HTMLImageElement (applies EXIF orientation like the browser does natively).
 * @param file - The picked image file.
 * @returns The decoded image element.
 * @throws If the file cannot be decoded as an image.
 */
function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = (): void => {
      URL.revokeObjectURL(url)
      resolve(image)
    }
    image.onerror = (): void => {
      URL.revokeObjectURL(url)
      reject(new Error('image-load-failed'))
    }
    image.src = url
  })
}

/**
 * Compute the target size, downscaling so the longest edge fits within the cap.
 * @param width - Source width.
 * @param height - Source height.
 * @param max - Longest-edge cap.
 * @returns The scaled width/height (unchanged when already small enough).
 */
function scaledSize(width: number, height: number, max: number): { width: number; height: number } {
  if (width <= max && height <= max) {
    return { width, height }
  }
  const ratio = Math.min(max / width, max / height)
  return { width: Math.round(width * ratio), height: Math.round(height * ratio) }
}

/**
 * Compress and re-encode a picked image to a small JPEG for chat attachment.
 * @param file - The image file from the picker or camera.
 * @returns A composer image with a preview data URL and its base64 payload.
 * @throws If the browser cannot decode or encode the image.
 */
export async function compressImageFile(file: File): Promise<ComposerImage> {
  const image = await loadImage(file)
  const { width, height } = scaledSize(image.naturalWidth, image.naturalHeight, MAX_DIMENSION)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('canvas-unsupported')
  }
  context.drawImage(image, 0, 0, width, height)

  const dataUrl = canvas.toDataURL('image/jpeg', JPEG_QUALITY)
  const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1)
  const name = file.name ? file.name.replace(/\.[^.]+$/, '.jpg') : 'image.jpg'

  return { id: crypto.randomUUID(), name, mime: 'image/jpeg', dataUrl, base64 }
}
