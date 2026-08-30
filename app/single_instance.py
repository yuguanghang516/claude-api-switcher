"""Windows single-instance guard for the desktop application."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


MUTEX_NAME = r"Local\ClaudeAPISwitcher.yuguanghang516.SingleInstance"
WINDOW_TITLE_PREFIX = "Claude API Switcher"
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9


class SingleInstanceGuard:
    """Own a version-independent named mutex for the current Windows session."""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self._kernel32 = None
        self._handle = None

    def acquire(self) -> bool:
        if os.name != "nt":
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not handle:
            raise OSError(error, "无法创建软件单实例互斥量")
        if error == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            self.focus_existing_window()
            return False
        self._kernel32 = kernel32
        self._handle = handle
        return True

    @staticmethod
    def focus_existing_window(title_prefix: str = WINDOW_TITLE_PREFIX) -> bool:
        """Bring the existing app window forward without sending it input."""
        if os.name != "nt":
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
        user32.EnumWindows.restype = wintypes.BOOL
        found = {"value": False}

        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, len(buffer))
            if buffer.value.startswith(title_prefix):
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
                found["value"] = True
                return False
            return True

        callback = callback_type(visit)
        user32.EnumWindows(callback, 0)
        return found["value"]

    def release(self) -> None:
        if self._handle and self._kernel32:
            self._kernel32.CloseHandle(self._handle)
        self._handle = None
        self._kernel32 = None

    def __enter__(self) -> "SingleInstanceGuard":
        if not self.acquire():
            raise RuntimeError("Claude API Switcher 已在运行")
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()
