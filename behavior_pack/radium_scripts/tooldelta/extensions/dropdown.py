# coding=utf-8
"""Control-local dropdown for tooldelta_lib.combo_box; no ViewBinder required."""
from radium_scripts.tooldelta.cli import CF, LEVEL_ID
from radium_scripts.tooldelta.utils.timer import ExecLater

if 0>1:
    import typing
    from radium_scripts.tooldelta.ui.elem_comp import UBaseCtrl, UButton

POOL_SIZE = 16  # tooldelta_lib.dropdown_content 中静态行 row_0..row_15 的数量, 改动需同步


class Dropdown(object):
    """Wrap one combo_box control. Indices start at zero; -1 means no selection.

    Keep this object on the owner and call Dispose before removing its controls.
    The parent must not clip children: the popup extends beyond the collapsed box.
    """

    def __init__(self, ctrl, placeholder=None, max_visible_options=6, row_height=25):
        # type: (UBaseCtrl, str | None, int, float) -> None
        if int(max_visible_options) < 1 or row_height <= 0:
            raise ValueError("Dropdown needs positive row height and visible count")
        self.ctrl = ctrl
        self._toggle = ctrl["toggle_button"].asButton()
        self._label = self._toggle["button_label"].asLabel()
        self._dismiss = ctrl["dismiss_button"].asButton()
        self._popup = ctrl["dropdown_panel"]
        self._content = self._popup["options_scroll"].asScrollView().GetContent()
        # 引擎不给运行时创建的控件传祖先变量, 因此选项行优先复用 JSON 里的静态行池,
        # 只有这些行才吃得到 combo_box 实例上的 $option_* 覆盖.
        try:
            self._pool = [
                self._content["row_%d" % index].asButton() for index in range(POOL_SIZE)
            ]
        except ValueError:
            raise ValueError(
                "tooldelta_lib.dropdown_content 的行池与 POOL_SIZE(%d) 不一致" % POOL_SIZE
            )
        self._pool_paths = set(row.base.GetPath() for row in self._pool)
        for row in self._pool:
            row.SetVisible(False)
        self._free_rows = list(self._pool)
        self._placeholder = self._label.GetText() if placeholder is None else placeholder
        self._max_visible = int(max_visible_options)
        self._row_height = float(row_height)
        self._options = []  # type: list[tuple[str, typing.Any]]
        self._rows = []  # type: list[UButton]
        self._selected = -1
        self._opened = False
        self._enabled = True
        self._disposed = False
        self._revision = 0
        self._next_row_id = 0
        self._callback = None  # type: typing.Callable[[int, str, typing.Any], None] | None
        self._toggle.SetCallback(self._on_toggle)
        self._dismiss.SetCallback(self._on_dismiss)
        self._popup.SetVisible(False)
        self._dismiss.SetVisible(False)
        self._label.SetText(self._placeholder or "")

    def AddOption(self, text, extra_data=None):
        # type: (str, typing.Any) -> int
        """Append a label/value pair and return its index; does not auto-select."""
        self._check_alive()
        self.Close()
        self._revision += 1
        row = self._acquire_row()
        row["button_label"].asLabel().SetText(text)
        self._rows.append(row)
        self._options.append((text, extra_data))
        self._refresh_rows()
        return len(self._options) - 1

    def RemoveOption(self, index):
        # type: (int) -> bool
        self._check_alive()
        if not 0 <= index < len(self._options):
            return False
        self.Close()
        self._revision += 1
        self._release_row(self._rows.pop(index))
        self._options.pop(index)
        if self._selected == index:
            self._selected = -1
        elif self._selected > index:
            self._selected -= 1
        self._refresh_rows()
        self._refresh_selection()
        return True

    def Clear(self):
        self._check_alive()
        self.Close()
        self._revision += 1
        self._release_rows()
        self._options = []
        self._selected = -1
        self._refresh_rows()
        self._refresh_selection()

    def GetOptionCount(self):
        return len(self._options)

    def GetSelectedOption(self):
        return self._selected

    def GetSelectedShowName(self):
        return self._options[self._selected][0] if self._selected >= 0 else None

    def GetSelectedData(self):
        return self._options[self._selected][1] if self._selected >= 0 else None

    def SetSelectedOption(self, index, notify=False):
        # type: (int, bool) -> None
        """Programmatic selection is silent by default; -1 clears selection."""
        self._check_alive()
        if not -1 <= index < len(self._options):
            raise IndexError("Dropdown option index out of range: %s" % index)
        self._revision += 1
        changed = index != self._selected
        self._selected = index
        self._refresh_selection()
        if changed and notify and index >= 0 and self._callback is not None:
            text, data = self._options[index]
            self._callback(index, text, data)

    def ClearSelection(self):
        self.SetSelectedOption(-1)

    def RegisterSelectItemCallback(self, callback):
        # type: (typing.Callable[[int, str, typing.Any], None] | None) -> None
        """Called on a changed selection, with (index, text, extra_data)."""
        self._check_alive()
        self._callback = callback

    def SetEnabled(self, enabled):
        # type: (bool) -> None
        self._check_alive()
        self._enabled = bool(enabled)
        if not self._enabled:
            self.Close()
        self._toggle.SetAlpha(1.0 if self._enabled else 0.5)

    def IsOpen(self):
        return self._opened

    def Open(self):
        # type: () -> bool
        self._check_alive()
        if self._opened or not self._enabled or not self._options:
            return False
        self._refresh_rows()
        x, y = self.ctrl.GetRootPos()
        # Resolution pixels cover at least the scaled UI canvas. Oversizing this
        # transparent click catcher is intentional; it is clipped by the screen.
        self._dismiss.SetPos((-x, -y))
        self._dismiss.SetSize(CF.CreateGame(LEVEL_ID).GetScreenSize())
        self._opened = True
        self._dismiss.SetVisible(True)
        self._popup.SetVisible(True)
        return True

    def Close(self):
        # type: () -> None
        if self._disposed or not self._opened:
            return
        self._opened = False
        self._revision += 1
        self._popup.SetVisible(False)
        self._dismiss.SetVisible(False)

    def Toggle(self):
        if self._opened:
            self.Close()
        else:
            self.Open()

    def Dispose(self, screen_destroyed=False):
        # type: (bool) -> None
        """Detach before reuse/removal; pass True from the owner's OnDestroy."""
        if self._disposed:
            return
        if not screen_destroyed:
            self.Close()
            self._toggle.SetCallback(_ignore_touch)
            self._toggle.SetAlpha(1.0)
            self._dismiss.SetCallback(_ignore_touch)
            self._release_rows()
            self._label.SetText(self._placeholder or "")
        self._disposed = True
        self._opened = False
        self._revision += 1
        self._callback = None
        self._rows = []
        self._options = []
        self._selected = -1

    def _acquire_row(self):
        # type: () -> UButton
        if self._free_rows:
            row = self._free_rows.pop()
            row.SetVisible(True)
            return row
        # 行池用尽: 运行时创建的行拿不到祖先变量, 改用自带默认值的独立定义兜底.
        row = self._content.AddElement(
            "tooldelta_lib.dropdown_option_standalone", "option_%d" % self._next_row_id
        ).asButton()
        self._next_row_id += 1
        return row

    def _release_row(self, row):
        # type: (UButton) -> None
        """Hide a pooled row for reuse; pooled rows must survive, only extras die."""
        if row.base.GetPath() in self._pool_paths:
            row.SetVisible(False)
            self._free_rows.append(row)
        else:
            row.Remove()

    def _release_rows(self):
        for row in self._rows:
            self._release_row(row)
        self._rows = []

    def _refresh_rows(self):
        width, height = self.ctrl.GetSize()
        visible_rows = min(len(self._rows), self._max_visible)
        # 弹层与主按钮严丝合缝: 顶端贴按钮底边, 左右同宽.
        popup_height = visible_rows * self._row_height
        self._popup.SetPos((0, height))
        # SetSize defaults to leaving children unchanged: resize the background
        # and scroll viewport along with the popup, then lay out content/rows.
        self._popup.SetSize((width, popup_height), resize_children=True)
        # 只有需要滚动时才缩窄内容, 给右侧滚动条让位.
        content_width = max(1, width - 10) if len(self._rows) > self._max_visible else width
        self._content.SetSize((content_width, max(1, len(self._rows) * self._row_height)))
        for index, row in enumerate(self._rows):
            # Keep button state images and selection highlight within this row.
            row.SetSize((content_width, self._row_height), resize_children=True)
            row.SetPos((0, index * self._row_height))
            row.SetCallback(self._make_option_callback(index))

    def _refresh_selection(self):
        text = self.GetSelectedShowName() if self._selected >= 0 else self._placeholder
        self._label.SetText(text or "")
        for index, row in enumerate(self._rows):
            row["selected_marker"].SetVisible(index == self._selected)

    def _make_option_callback(self, index):
        def on_touch(args):
            if not self._disposed and self._enabled and self._opened:
                # Never hide/remove a scroll view from inside its button callback.
                ExecLater(0, self._confirm_option, index, self._revision)
        return on_touch

    def _confirm_option(self, index, revision):
        if (self._disposed or not self._enabled or not self._opened
                or revision != self._revision):
            return
        self.Close()
        self.SetSelectedOption(index, notify=True)

    def _on_toggle(self, args):
        if not self._disposed:
            self.Toggle()

    def _on_dismiss(self, args):
        self.Close()

    def _check_alive(self):
        if self._disposed:
            raise RuntimeError("Dropdown has been disposed")


def _ignore_touch(args):
    pass


__all__ = ["Dropdown"]
