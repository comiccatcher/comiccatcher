import flet as ft
from config import ConfigManager
from ui.snack import show_snack

COLORS = getattr(ft, "colors", ft.Colors)

class SettingsView(ft.Column):
    def __init__(self, page: ft.Page, config_manager: ConfigManager):
        super().__init__()
        # Store a reference; do not assign to Control.page.
        self._page = page
        self.config_manager = config_manager
        self.expand = True

        self.scroll_method_radio = ft.RadioGroup(
            content=ft.Column([
                ft.Radio(value="infinite", label="Infinite Scroll (Sequential)"),
                ft.Radio(value="paging", label="Traditional Paging (Standard Buttons)"),
                ft.Radio(value="viewport", label="Viewport Paging (Fit to Window)"),
            ]),
            value=self.config_manager.get_scroll_method(),
            on_change=self.on_scroll_method_change
        )

        self.library_dir_field = ft.TextField(
            label="Library folder",
            value=str(self.config_manager.get_library_dir()),
            hint_text="Where downloaded and local comics live (default: ~/ComicCatcher)",
            dense=True,
        )
        self.save_library_btn = ft.OutlinedButton("Save Library Folder", on_click=self.on_save_library_dir)

        self.controls = [
            ft.Text("App Settings", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("Browsing Method", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("Choose how you want to browse large collections:", size=14, color=COLORS.GREY_500),
            self.scroll_method_radio,
            ft.Divider(),
            ft.Text("Library", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("Local folder for downloaded and imported comics:", size=14, color=COLORS.GREY_500),
            self.library_dir_field,
            self.save_library_btn,
            ft.Divider(),
            ft.Text("About", size=18, weight=ft.FontWeight.BOLD),
            ft.Text("ComicCatcher v0.1.0", size=14),
        ]

    def on_scroll_method_change(self, e):
        self.config_manager.set_scroll_method(self.scroll_method_radio.value)
        show_snack(self._page, f"Scroll method updated to: {self.scroll_method_radio.value}")

    def on_save_library_dir(self, e):
        path_str = (self.library_dir_field.value or "").strip()
        self.config_manager.set_library_dir(path_str)
        # Normalize what we display (expanduser/resolve).
        self.library_dir_field.value = str(self.config_manager.get_library_dir())
        try:
            self.library_dir_field.update()
        except Exception:
            pass
        show_snack(self._page, f"Library folder set to: {self.library_dir_field.value}")
