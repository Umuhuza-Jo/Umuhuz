import flet as ft

def main(page: ft.Page):
    page.title = "Hello, Flet!"
    page.add(
        ft.Text("Welcome to your Flet web app! 🚀")
    )

if __name__ == "__main__":
    ft.app(target=main)
