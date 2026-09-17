"""App-local CTk facade: smooth outlined widgets without patching the library."""
import customtkinter as _native
from .smooth_widgets import SmoothButton as CTkButton
from .smooth_widgets import SmoothFrame as CTkFrame
from .smooth_widgets import SmoothComboBox as CTkComboBox


def __getattr__(name):
    return getattr(_native, name)
