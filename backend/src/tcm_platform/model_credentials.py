"""Store provider secrets in Windows Credential Manager without a runtime dependency."""

import ctypes
import os
from ctypes import wintypes

_SERVICE = "tcm-research-platform"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168
_MAX_BLOB_BYTES = 2560


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _credential_api():
    if os.name != "nt":
        raise RuntimeError("Windows Credential Manager is unavailable on this platform")
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def _target(provider: str) -> str:
    if provider not in {"aliyun", "siliconflow", "deepseek"}:
        raise ValueError("unknown model provider")
    return f"{_SERVICE}:{provider}"


def read_model_key(provider: str) -> str | None:
    api = _credential_api()
    pointer = ctypes.POINTER(_CREDENTIALW)()
    if not api.CredReadW(_target(provider), _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == _ERROR_NOT_FOUND:
            return None
        raise OSError(error, "Windows Credential Manager read failed")
    try:
        credential = pointer.contents
        if not credential.CredentialBlobSize:
            return None
        blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return blob.decode("utf-16-le")
    finally:
        api.CredFree(pointer)


def store_model_key(provider: str, key: str) -> None:
    if not key:
        raise ValueError("empty API key")
    encoded = key.encode("utf-16-le")
    if len(encoded) > _MAX_BLOB_BYTES:
        raise ValueError("model API key exceeds Credential Manager size limit")
    api = _credential_api()
    blob = ctypes.create_string_buffer(encoded)
    credential = _CREDENTIALW()
    credential.Type = _CRED_TYPE_GENERIC
    credential.TargetName = _target(provider)
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = _SERVICE
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise OSError(ctypes.get_last_error(), "Windows Credential Manager write failed")
