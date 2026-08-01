"""
Message image attachments — materialize PWA-sent images into the project clone.

Images arrive in the run payload as base64 (compressed client-side). Before invoking the
provider CLI we decode them into ``<cwd>/.nightforge/attachments/`` and append their paths to
the prompt, so Claude Code / Cursor read them with their file-reading tools. The attachments
directory is added to the repo's local git exclude so it never dirties ``git status``.
"""
from __future__ import annotations

import base64
import binascii
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

ATTACHMENTS_DIR = os.path.join(".nightforge", "attachments")

#: MIME → file extension for the formats a phone camera / library realistically produces.
_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


def _extension_for_mime(mime: Optional[str]) -> str:
    """Return a file extension for an image MIME type, defaulting to ``.jpg``."""
    return _EXTENSION_BY_MIME.get((mime or "").strip().lower(), ".jpg")


def _decode_base64(data: str) -> Optional[bytes]:
    """Decode base64 image data, tolerating a leading ``data:`` URL prefix."""
    payload = data.strip()
    if payload.startswith("data:"):
        _, _, payload = payload.partition(",")
    try:
        return base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as exc:
        logger.warning("Skipping image attachment with invalid base64: %s", exc)
        return None


def _ensure_git_excluded(cwd: str) -> None:
    """Add ``.nightforge/`` to the repo's local git exclude so attachments stay untracked."""
    git_dir = os.path.join(cwd, ".git")
    if not os.path.isdir(git_dir):
        return
    exclude_path = os.path.join(git_dir, "info", "exclude")
    entry = ".nightforge/"
    try:
        existing = ""
        if os.path.isfile(exclude_path):
            with open(exclude_path, "r", encoding="utf-8") as handle:
                existing = handle.read()
        if entry in existing.split():
            return
        os.makedirs(os.path.dirname(exclude_path), exist_ok=True)
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        with open(exclude_path, "a", encoding="utf-8") as handle:
            handle.write(f"{prefix}{entry}\n")
    except OSError as exc:
        logger.debug("Could not update git exclude for attachments: %s", exc)


def materialize_images(cwd: str, images: list[dict], *, prefix: str = "") -> list[str]:
    """
    Write base64 images from a message payload into the project clone.

    Args:
        cwd: The project working directory (where the CLI runs).
        images: Payload image dicts with ``mime``, ``filename`` and base64 ``data``.
        prefix: Short token (e.g. the message id) to keep file names unique across messages.

    Returns:
        The written attachments' paths, relative to ``cwd`` with forward slashes.
    """
    if not images:
        return []

    target_dir = os.path.join(cwd, ATTACHMENTS_DIR)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create attachments directory: %s", exc)
        return []

    relative_paths: list[str] = []
    for index, image in enumerate(images):
        raw = _decode_base64(str(image.get("data") or ""))
        if not raw:
            continue
        extension = _extension_for_mime(image.get("mime"))
        name = f"nf-{prefix or 'msg'}-{index}{extension}"
        try:
            with open(os.path.join(target_dir, name), "wb") as handle:
                handle.write(raw)
        except OSError as exc:
            logger.warning("Could not write image attachment %s: %s", name, exc)
            continue
        relative_paths.append(f"{ATTACHMENTS_DIR}/{name}".replace(os.sep, "/"))

    if relative_paths:
        _ensure_git_excluded(cwd)
    return relative_paths


def augment_prompt_with_images(prompt: str, relative_paths: list[str]) -> str:
    """
    Append attached-image paths to a prompt so the CLI reads and considers them.

    Args:
        prompt: The user's message text.
        relative_paths: Image paths relative to the working directory.

    Returns:
        The prompt with an image section appended (unchanged when there are no images).
    """
    if not relative_paths:
        return prompt

    listing = "\n".join(f"- {path}" for path in relative_paths)
    section = (
        "Images jointes à ce message (ouvre-les et prends-les en compte) :\n"
        f"{listing}"
    )
    return f"{prompt}\n\n{section}" if prompt.strip() else section
