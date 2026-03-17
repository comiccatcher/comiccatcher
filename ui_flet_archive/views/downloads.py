import flet as ft
from api.download_manager import DownloadManager, DownloadTask

COLORS = getattr(ft, "colors", ft.Colors)
SURFACE_VARIANT = getattr(COLORS, "SURFACE_VARIANT", getattr(COLORS, "SURFACE_CONTAINER", COLORS.SURFACE))

class DownloadsView(ft.Column):
    def __init__(self, page: ft.Page, download_manager: DownloadManager):
        super().__init__()
        # Store a reference; do not assign to Control.page.
        self._page = page
        self.dm = download_manager
        self.expand = True
        
        self.tasks_list = ft.ListView(expand=True, spacing=10)
        
        self.controls = [
            ft.Text("Active Downloads", size=24, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=self.tasks_list,
                expand=True,
                padding=10
            )
        ]
        
        self.dm.set_callback(self.refresh_tasks)
        self.refresh_tasks()

    def refresh_tasks(self):
        self.tasks_list.controls.clear()
        
        if not self.dm.tasks:
            self.tasks_list.controls.append(
                ft.Container(
                    content=ft.Text("No active or recent downloads.", color=COLORS.GREY_500),
                    alignment=ft.alignment.center,
                    padding=50
                )
            )
        else:
            for task_id, task in reversed(list(self.dm.tasks.items())):
                self.tasks_list.controls.append(self._create_task_row(task))
        
        try:
            self.update()
        except:
            pass

    def _create_task_row(self, task: DownloadTask):
        status_color = COLORS.BLUE_400
        if task.status == "Completed": status_color = COLORS.GREEN_400
        if task.status == "Failed": status_color = COLORS.ERROR
        
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.FILE_DOWNLOAD, color=status_color),
                    ft.Column([
                        ft.Text(task.title, weight=ft.FontWeight.BOLD, size=14),
                        ft.Text(f"Status: {task.status}", size=12, color=status_color),
                    ], expand=True),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, on_click=lambda _: self.dm.remove_task(task.book_id), icon_size=18)
                ]),
                ft.ProgressBar(value=task.progress, color=status_color, bgcolor=COLORS.GREY_800),
                ft.Text(task.error, color=COLORS.ERROR, size=10, visible=task.error is not None)
            ], spacing=5),
            padding=15,
            border=ft.border.all(1, COLORS.OUTLINE_VARIANT),
            border_radius=10,
            bgcolor=SURFACE_VARIANT
        )
