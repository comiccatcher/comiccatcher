import sys
import ctypes
from ctypes import wintypes

# Windows Constants
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_BORDER = 0x00800000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

# DWM Constants
DWMWA_NCRENDERING_POLICY = 2
DWMWA_TRANSITIONS_FORCEDISABLED = 3
DWMNCRP_DISABLED = 1
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWA_COLOR_NONE = 0xFFFFFFFE
DWMSBT_NONE = 1

# SWP Constants
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

def _get_win_funcs():
    """Helper to get 32/64-bit compatible User32 functions."""
    user32 = ctypes.windll.user32
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        SetWindowLongPtr = user32.SetWindowLongPtrW
        SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        SetWindowLongPtr.restype = ctypes.c_ssize_t
        
        GetWindowLongPtr = user32.GetWindowLongPtrW
        GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
        GetWindowLongPtr.restype = ctypes.c_ssize_t
    else:
        SetWindowLongPtr = user32.SetWindowLongW
        SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
        SetWindowLongPtr.restype = wintypes.LONG
        
        GetWindowLongPtr = user32.GetWindowLongW
        GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
        GetWindowLongPtr.restype = wintypes.LONG
    return GetWindowLongPtr, SetWindowLongPtr

def apply_windows_fullscreen_fix(win_id: int, is_fullscreen: bool):
    """
    Applies Windows-specific tweaks to remove the 1px border and rounded corners
    often seen on Windows 11 in fullscreen mode.
    """
    if sys.platform != "win32":
        return

    try:
        hwnd = int(win_id)
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        GetWindowLongPtr, SetWindowLongPtr = _get_win_funcs()

        # 1. Handle Window Styles
        style = GetWindowLongPtr(hwnd, GWL_STYLE)
        if is_fullscreen:
            # Strip borders and frame
            style &= ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        
        SetWindowLongPtr(hwnd, GWL_STYLE, style)

        # 2. Handle Windows 11 Rounded Corners
        pref = DWMWCP_DONOTROUND if is_fullscreen else DWMWCP_DEFAULT
        pref_value = ctypes.c_int(pref)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref_value),
            ctypes.sizeof(pref_value)
        )

        # 3. Force frame update
        user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        )

    except Exception:
        pass

def apply_windows_popover_fix(win_id: int):
    """
    Removes the Windows 11 native thick border and shadow from popovers.
    Forcefully strips frame styles that DWM renders as glassy borders.
    """
    if sys.platform != "win32":
        return

    try:
        hwnd = int(win_id)
        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        GetWindowLongPtr, SetWindowLongPtr = _get_win_funcs()

        # 0. Disable Non-Client Rendering Policy to strip default OS shadows and borders entirely
        ncr_policy = ctypes.c_int(DWMNCRP_DISABLED)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_NCRENDERING_POLICY,
            ctypes.byref(ncr_policy),
            ctypes.sizeof(ncr_policy)
        )

        # 1. Force strip of any thick frame or border styles that Win11 renders as "glassy"
        style = GetWindowLongPtr(hwnd, GWL_STYLE)
        style &= ~(WS_CAPTION | WS_THICKFRAME | WS_BORDER)
        SetWindowLongPtr(hwnd, GWL_STYLE, style)

        # 2. Disable window transitions to prevent the "flash" of borders on appear
        transitions = ctypes.c_int(1) # True
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_TRANSITIONS_FORCEDISABLED,
            ctypes.byref(transitions),
            ctypes.sizeof(transitions)
        )

        # 3. Remove the native Windows 11 border color
        border_color = ctypes.c_int(DWMWA_COLOR_NONE)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_BORDER_COLOR,
            ctypes.byref(border_color),
            ctypes.sizeof(border_color)
        )

        # 4. Set corner preference to square
        pref = ctypes.c_int(DWMWCP_DONOTROUND)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref),
            ctypes.sizeof(pref)
        )

        # 5. Disable any system backdrops (Acrylic/Mica)
        backdrop = ctypes.c_int(DWMSBT_NONE)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop),
            ctypes.sizeof(backdrop)
        )

        # 6. Force frame update to apply style changes
        user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        )

    except Exception:
        pass
