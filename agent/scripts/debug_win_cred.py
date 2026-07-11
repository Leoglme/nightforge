"""Try reading Claude OAuth from Windows Credential Manager."""
from __future__ import annotations

import ctypes
import json
import sys
from ctypes import wintypes

CRED_TYPE_GENERIC = 1


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_cred(target: str) -> str | None:
    advapi32 = ctypes.windll.advapi32
    pcred = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
        return None
    try:
        blob = ctypes.string_at(pcred.contents.CredentialBlob, pcred.contents.CredentialBlobSize)
        return blob.decode("utf-8", errors="replace")
    finally:
        advapi32.CredFree(pcred)


def main() -> None:
    if sys.platform != "win32":
        print("not windows")
        return
    for target in ("Claude Code-credentials", "Claude Code"):
        raw = read_cred(target)
        print(target, "->", "found" if raw else "missing")
        if not raw:
            continue
        print("len", len(raw))
        try:
            data = json.loads(raw)
            oauth = data.get("claudeAiOauth", data)
            print("keys", list(oauth.keys()) if isinstance(oauth, dict) else type(oauth))
            if isinstance(oauth, dict):
                print("has refresh", bool(oauth.get("refreshToken")))
        except json.JSONDecodeError:
            print("preview", raw[:120])


if __name__ == "__main__":
    main()
