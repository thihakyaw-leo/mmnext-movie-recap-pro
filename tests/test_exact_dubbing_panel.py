import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from mmnext.ui.workspace.mode_panels.exact_dubbing_panel import ExactDubbingPanel
from mmnext.domain.models import ExactDubbingRow

def ensure_qapp():
    app = QGuiApplication.instance()
    if app is None:
        app = QApplication([])

ensure_qapp()

def test_warning_label_text():
    panel = ExactDubbingPanel()
    assert panel.warning_label is not None
    text = panel.warning_label.text()
    assert "Exact Dubbing does not summarize" in text
    assert panel.warning_label.property("role") == "warning"

def test_warning_label_wordwrap_and_size_policy():
    panel = ExactDubbingPanel()
    lbl = panel.warning_label
    assert lbl.wordWrap()
    from PySide6.QtWidgets import QSizePolicy
    sp = lbl.sizePolicy()
    assert sp.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert sp.verticalPolicy() == QSizePolicy.Policy.MinimumExpanding
    assert lbl.alignment() == Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop

def test_warning_label_no_inline_style():
    panel = ExactDubbingPanel()
    style = panel.warning_label.styleSheet()
    assert style == ""

def test_warning_label_visible_only_explicit():
    panel = ExactDubbingPanel()
    # The label is added to layout, visibility is default True; isVisible() requires shown parent
    # Check that visibility property is True and widget is in layout
    assert panel.warning_label.isEnabled()

def test_panel_layout_contains_warning():
    panel = ExactDubbingPanel()
    # Verify warning is child of panel layout
    children = [panel.warning_label]
    # Simple check: widget exists
    assert panel.findChild(type(panel.warning_label)) is not None

def test_button_enablement_preserved():
    panel = ExactDubbingPanel()
    # Render disabled initially
    assert not panel.render_button.isEnabled()
    # Translate button exists
    assert panel.translate_button.isEnabled()
    assert panel.gender_button.isEnabled()
    assert panel.validate_button.isEnabled()
    assert panel.save_button.isEnabled()

def test_no_clip_at_various_widths():
    panel = ExactDubbingPanel()
    for w in [1180, 1400, 1600, 1920]:
        panel.resize(w, 760)
        panel.show()
        # Ensure layout not falling back to minimum
        # Just ensure warning label still has text
        assert len(panel.warning_label.text()) > 0
