import flet as ft
from config import ConfigManager
from models.server import ServerProfile

COLORS = getattr(ft, "colors", ft.Colors)

class ServersView(ft.Column):
    def __init__(self, page: ft.Page, config_manager: ConfigManager, on_profile_selected):
        super().__init__()
        # Store a reference; do not assign to Control.page.
        self._page = page
        self.config_manager = config_manager
        self.on_profile_selected = on_profile_selected
        self.expand = True
        self.editing_profile_id = None

        self.profiles_list = ft.ListView(expand=True, spacing=10)
        
        self.name_input = ft.TextField(label="Server Name", expand=True)
        self.url_input = ft.TextField(label="Server URL (e.g., https://komga.example.com)", expand=True)
        self.user_input = ft.TextField(label="Username (optional)", expand=True)
        self.pass_input = ft.TextField(label="Password (optional)", password=True, can_reveal_password=True, expand=True)
        self.token_input = ft.TextField(label="Bearer Token (optional)", password=True, can_reveal_password=True, expand=True)

        self.save_button = ft.ElevatedButton("Add Profile", on_click=self.save_profile)
        self.cancel_button = ft.TextButton("Cancel Edit", on_click=self.cancel_edit, visible=False)

        self.controls = [
            ft.Text("Server Profiles", size=24, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=self.profiles_list,
                expand=True,
                border=ft.border.all(1, COLORS.OUTLINE),
                border_radius=5,
                padding=10
            ),
            ft.Divider(),
            ft.Text("Add / Edit Profile", size=20, weight=ft.FontWeight.BOLD),
            ft.Row([self.name_input, self.url_input]),
            ft.Row([self.user_input, self.pass_input]),
            self.token_input,
            ft.Row([self.save_button, self.cancel_button])
        ]
        
        self.refresh_profiles()

    def _safe_update(self):
        try:
            if self.page:
                self.update()
        except:
            pass

    def refresh_profiles(self):
        self.profiles_list.controls.clear()
        for p in self.config_manager.profiles:
            self.profiles_list.controls.append(
                ft.GestureDetector(
                    content=ft.ListTile(
                        title=ft.Text(p.name),
                        subtitle=ft.Text(p.url),
                        leading=ft.Icon(ft.Icons.DNS),
                        trailing=ft.Row([
                            ft.IconButton(ft.Icons.LOGIN, on_click=lambda e, profile=p: self.on_profile_selected(profile), tooltip="Browse"),
                            ft.IconButton(ft.Icons.EDIT, on_click=lambda e, profile=p: self.start_edit(profile), tooltip="Edit"),
                            ft.IconButton(ft.Icons.DELETE, on_click=lambda e, profile_id=p.id: self.delete_profile(profile_id), tooltip="Delete", icon_color=COLORS.ERROR)
                        ], tight=True),
                    ),
                    on_double_tap=lambda e, profile=p: self.on_profile_selected(profile)
                )
            )
        self._safe_update()

    def start_edit(self, profile: ServerProfile):
        self.editing_profile_id = profile.id
        self.name_input.value = profile.name
        self.url_input.value = profile.url
        self.user_input.value = profile.username or ""
        self.pass_input.value = profile.password or ""
        self.token_input.value = profile.bearer_token or ""
        
        self.save_button.text = "Update Profile"
        self.cancel_button.visible = True
        self._safe_update()

    def cancel_edit(self, e):
        self.editing_profile_id = None
        self.name_input.value = ""
        self.url_input.value = ""
        self.user_input.value = ""
        self.pass_input.value = ""
        self.token_input.value = ""
        
        self.save_button.text = "Add Profile"
        self.cancel_button.visible = False
        self._safe_update()

    def save_profile(self, e):
        if not self.name_input.value or not self.url_input.value:
            return
            
        if self.editing_profile_id:
            profile = self.config_manager.get_profile(self.editing_profile_id)
            if profile:
                profile.name = self.name_input.value
                profile.url = self.url_input.value
                profile.username = self.user_input.value or None
                profile.password = self.pass_input.value or None
                profile.bearer_token = self.token_input.value or None
                self.config_manager.update_profile(profile)
        else:
            self.config_manager.add_profile(
                name=self.name_input.value,
                url=self.url_input.value,
                username=self.user_input.value or None,
                password=self.pass_input.value or None,
                token=self.token_input.value or None
            )
        
        self.cancel_edit(None)
        self.refresh_profiles()

    def delete_profile(self, profile_id):
        self.config_manager.remove_profile(profile_id)
        self.refresh_profiles()
