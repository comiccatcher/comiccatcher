import flet as ft


def show_snack(page: ft.Page, message: str, *, text_color=None, bgcolor=None):
    """
    Flet 0.82+ removed Page.show_snack_bar(). Use a single SnackBar instance in page.overlay.
    """
    if page is None:
        return

    snack = getattr(page, "_comiccatcher_snack", None)
    if snack is None:
        snack = ft.SnackBar(content=ft.Text(message, color=text_color), bgcolor=bgcolor, open=True)
        setattr(page, "_comiccatcher_snack", snack)
        try:
            page.overlay.append(snack)
        except Exception:
            return
    else:
        snack.content = ft.Text(message, color=text_color)
        snack.bgcolor = bgcolor
        snack.open = True

    try:
        page.update()
    except Exception:
        pass

