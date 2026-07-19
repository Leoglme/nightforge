"""
Symmetric encryption for secrets (Cursor tokens, passwords, API keys).

Uses Fernet — same pattern as DevLeadHunter. Requires ENCRYPTION_KEY in env
(generate: ``python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"``).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class EncryptionService:
    """Encrypt / decrypt sensitive strings with a Fernet key."""

    def __init__(self, encryption_key: Optional[str] = None) -> None:
        """
        Args:
            encryption_key: Base64 Fernet key. Falls back to settings / env.
        """
        if encryption_key:
            self.key = encryption_key.encode()
        else:
            try:
                from core.config import settings

                env_key = settings.encryption_key
            except Exception:  # noqa: BLE001
                env_key = os.getenv("ENCRYPTION_KEY")

            if env_key:
                self.key = env_key.encode()
            else:
                logger.warning(
                    "No ENCRYPTION_KEY set — generating an ephemeral Fernet key "
                    "(secrets will not survive restart). Set ENCRYPTION_KEY in .env."
                )
                self.key = Fernet.generate_key()
                logger.warning("Ephemeral ENCRYPTION_KEY=%s", self.key.decode())

        self.cipher = Fernet(self.key)

    def encrypt(self, data: str) -> str:
        """
        Encrypt a UTF-8 string.

        Args:
            data: Plaintext.

        Returns:
            Fernet token as a string (empty if data is empty).
        """
        if not data:
            return ""
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt a Fernet token string.

        Args:
            encrypted_data: Ciphertext from ``encrypt``.

        Returns:
            Plaintext (empty if input empty).

        Raises:
            ValueError: If decryption fails.
        """
        if not encrypted_data:
            return ""
        try:
            return self.cipher.decrypt(encrypted_data.encode()).decode()
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Failed to decrypt data: {exc}") from exc

    @staticmethod
    def generate_key() -> str:
        """Return a new Fernet key as a UTF-8 string."""
        return Fernet.generate_key().decode()


encryption_service = EncryptionService()
