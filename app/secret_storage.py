"""Windows current-user DPAPI protection for gateway credentials at rest."""
import base64
import ctypes
import os
from ctypes import wintypes

PREFIX = "dpapi:v1:"


class SecretProtectionError(OSError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data: bytes, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise SecretProtectionError("网关密钥加密需要 Windows；未写入任何明文密钥。")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _Blob()
    # UI_FORBIDDEN, current user only. Never CRYPTPROTECT_LOCAL_MACHINE.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise SecretProtectionError("无法保护或读取网关密钥，请使用原 Windows 账户；原配置未清空。")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.memset(output.data, 0, output.size)
        kernel32.LocalFree(output.data)


def protect_secret(value: str) -> str:
    if not isinstance(value, str):
        raise SecretProtectionError("API 密钥必须是文本。")
    if not value:
        return ""
    return PREFIX + base64.b64encode(_crypt(value.encode("utf-8"), False)).decode("ascii")


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    if not isinstance(value, str) or not value.startswith(PREFIX):
        raise SecretProtectionError("网关密钥格式不正确，原配置已保留。")
    try:
        return _crypt(base64.b64decode(value[len(PREFIX):], validate=True), True).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise SecretProtectionError("网关密钥已损坏或不属于当前账户，原配置已保留。") from exc
