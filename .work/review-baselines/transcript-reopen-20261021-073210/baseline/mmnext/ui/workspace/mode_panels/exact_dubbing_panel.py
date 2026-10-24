"""Exact Dubbing Mode control panel.

Exact dubbing works on a *one-row-per-source-line* table. Nothing may be
summarised, omitted, reordered or merged, so the panel only offers actions
that preserve the row contract: translate, re-detect the speaker, validate
and save.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....domain.models import ExactDubbingRow
from ...theme.palette import Palette
from ...widgets.badge import StateBadge

__all__ = ["ExactDubbingPanel"]


class ExactDubbingPanel(QWidget):
    """Actions and counters for Exact Dubbing Mode."""

    translateRequested = Signal()
    detectGenderRequested = Signal()
    saveRequested = Signal()
    validateRequested = Signal()
    renderRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.title = QLabel("EXACT DUBBING TABLE")
        self.title.setProperty("role", "sectionTitle")

        self.warning_label = QLabel("Exact Dubbing does not summarize, omit, reorder, or merge source dialogue. Every source row is preserved with immutable id, original, start, and duration.")
        self.warning_label.setProperty("role", "muted")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #ffb020;")

        self.row_count = QLabel("0 rows")
        self.row_count.setProperty("role", "muted")

        self.missing_badge = StateBadge("0 missing", Palette.SUCCESS)
        self.missing_badge.setToolTip(
            "Rows without a Burmese translation block the render."
        )

        self.unknown_badge = StateBadge("0 unknown speaker", Palette.SUCCESS)
        self.unknown_badge.setToolTip(
            "Unknown speakers fall back to my-MM-NilarNeural."
        )

        self.validation_badge = StateBadge("Not validated", Palette.WARNING)
        self.validation_badge.setToolTip(
            "Validate the exact-dubbing table before rendering."
        )

        self.translate_button = QPushButton("Translate all rows")
        self.translate_button.setProperty("variant", "ghost")
        self.translate_button.setToolTip(
            "Simulated in milestone 1 - no translation service is called."
        )
        self.translate_button.clicked.connect(self.translateRequested)

        self.gender_button = QPushButton("Detect speaker")
        self.gender_button.setProperty("variant", "ghost")
        self.gender_button.setToolTip(
            "Simulated in milestone 1 - gender comes from the source speaker."
        )
        self.gender_button.clicked.connect(self.detectGenderRequested)

        self.validate_button = QPushButton("Validate")
        self.validate_button.setProperty("variant", "ghost")
        self.validate_button.clicked.connect(self.validateRequested)

        self.save_button = QPushButton("Save translations")
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self.saveRequested)

        self.render_button = QPushButton("Render")
        self.render_button.setProperty("variant", "primary")
        self.render_button.setEnabled(False)
        self.render_button.setToolTip(
            "Render is enabled only after validation succeeds with no errors."
        )
        self.render_button.clicked.connect(self.renderRequested)

        layout.addWidget(self.title)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.row_count)
        layout.addWidget(self.missing_badge)
        layout.addWidget(self.unknown_badge)
        layout.addWidget(self.validation_badge)
        layout.addStretch(1)
        layout.addWidget(self.translate_button)
        layout.addWidget(self.gender_button)
        layout.addWidget(self.validate_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.render_button)

    # -- state --------------------------------------------------------------- #
    def set_rows(self, rows: list[ExactDubbingRow]) -> None:
        missing = sum(1 for row in rows if not row.burmese.strip())
        unknown = sum(1 for row in rows if row.gender.value == "unknown")
        edited = sum(1 for row in rows if row.edited)

        self.row_count.setText(
            f"{len(rows)} rows  |  {len(rows) - missing} translated  |  "
            f"{edited} edited"
        )
        if missing:
            self.missing_badge.set_state(f"{missing} missing", Palette.DANGER)
        else:
            self.missing_badge.set_state("0 missing", Palette.SUCCESS)
        if unknown:
            self.unknown_badge.set_state(
                f"{unknown} unknown speaker", Palette.WARNING
            )
        else:
            self.unknown_badge.set_state("0 unknown speaker", Palette.SUCCESS)
        self.save_button.setEnabled(edited > 0)
        # Reset validation state when rows change
        self.validation_badge.set_state("Not validated", Palette.WARNING)
        self.render_button.setEnabled(False)

    def update_validation(self, report) -> None:
        """Update panel UI based on a ValidationReport."""
        from ....domain.enums import Severity
        from ....domain.models import ValidationReport

        if not isinstance(report, ValidationReport):
            # Reset to not validated
            self.validation_badge.set_state("Not validated", Palette.WARNING)
            self.render_button.setEnabled(False)
            self.save_button.setEnabled(self.save_button.isEnabled())
            return

        errors = [i for i in report.issues if i.severity is Severity.ERROR]
        warnings = [i for i in report.issues if i.severity is Severity.WARNING]

        if errors:
            self.validation_badge.set_state(f"{len(errors)} error(s)", Palette.DANGER)
            self.render_button.setEnabled(False)
            self.save_button.setEnabled(False)
        else:
            if warnings:
                self.validation_badge.set_state(f"{len(warnings)} warning(s)", Palette.WARNING)
                self.render_button.setEnabled(True)
                # Save may remain enabled if edits exist
            else:
                self.validation_badge.set_state("Validated OK", Palette.SUCCESS)
                self.render_button.setEnabled(True)
        # Save should also be blocked when validation errors exist
        # (edited count already considered)

