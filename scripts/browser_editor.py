"""Enter scene source through CodeMirror's normal keyboard input path."""

from playwright.sync_api import Page


def fill_editor(page: Page, source: str) -> None:
    editor = page.get_by_role("textbox", name="Scene DSL editor", exact=True)
    editor.focus()
    editor.press("ControlOrMeta+a")
    page.keyboard.insert_text(source)
