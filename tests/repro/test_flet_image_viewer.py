#!/usr/bin/env python3
import argparse

import flet as ft

# Simple base64 PNG (transparent red square) so we only rely on the raw payload.
TEST_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAIAAAD/gAIDAAAAJElEQVR4nO3BMQEAAADCoPVPbQhPoAAAAAAAAAAA"
    "AAAAAAAAADwF6gAAVFpY+gAAAABJRU5ErkJggg=="
)


def main(page: ft.Page):
    page.title = "Flet Image Viewer Test"
    page.add(
        ft.Column(
            [
                ft.Text("Flet Image Test", size=24),
                ft.Container(
                    content=ft.Image(src=TEST_IMAGE_B64, width=200, height=200),
                    padding=20,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            expand=True,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--web", action="store_true")
    args = parser.parse_args()

    view = ft.AppView.FLET_APP_WEB if args.web else ft.AppView.FLET_APP
    ft.run(main, view=view, host=args.host, port=args.port)
