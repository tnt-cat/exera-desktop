import extera_engine


def _show(kind, text, **extra):
    host = extera_engine.host
    host.run_on_ui(lambda: host.show_bulletin(kind, str(text), extra or None))


class BulletinHelper:
    DURATION_SHORT = 1500
    DURATION_LONG = 2750
    DURATION_PROLONG = 5000

    @classmethod
    def show_info(cls, message, fragment=None):
        _show("info", message)

    @classmethod
    def show_error(cls, message, fragment=None):
        _show("error", message)

    @classmethod
    def show_success(cls, message, fragment=None):
        _show("success", message)

    @classmethod
    def show_simple(cls, text, icon_res_id=0, fragment=None):
        _show("info", text)

    @classmethod
    def show_two_line(cls, title, subtitle, icon_res_id=0, fragment=None):
        _show("info", title, subtitle=str(subtitle))

    @staticmethod
    def show_with_button(text, icon_res_id=0, button_text="", on_click=None,
                         fragment=None, duration=5000):
        _show("info", text, button=str(button_text), on_click=on_click)

    @classmethod
    def show_undo(cls, text, on_undo, on_action=None, subtitle=None, fragment=None):
        _show("info", text, button="Undo", on_click=on_undo, on_action=on_action)

    @classmethod
    def show_copied_to_clipboard(cls, message=None, fragment=None):
        _show("info", message or "Copied to clipboard")

    @classmethod
    def show_link_copied(cls, is_private_link_info=False, fragment=None):
        _show("info", "Link copied")

    @classmethod
    def show_file_saved_to_downloads(cls, file_type_enum_name="UNKNOWN", amount=1, fragment=None):
        _show("info", "Saved to downloads")

    @classmethod
    def show_file_saved_to_gallery(cls, is_video=False, amount=1, fragment=None):
        _show("info", "Saved")
