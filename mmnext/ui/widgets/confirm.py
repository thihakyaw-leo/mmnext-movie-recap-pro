"""Confirmation dialogs for destructive actions.

The milestone-1 rule from ``instructions.md`` is: *show a confirmation only
for destructive actions such as deleting a job or discarding unsaved
edits*. Everything else - navigating, switching modes, running a job -
happens without a dialog.

The dialog lives here so the main window and the settings screen ask the
same question in the same words, and so the test suite has a single seam
to patch: :func:`confirm_unsaved_changes`.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from ..app_context import AppContext

__all__ = ["UnsavedChoice", "confirm_unsaved_changes", "confirm_before_discard"]


class UnsavedChoice(Enum):
    """What the user chose in the unsaved-changes dialog."""

    #: Keep the edits (they are marked as saved) and continue.
    SAVE = "save"
    #: Throw the edits away and continue.
    DISCARD = "discard"
    #: Do not perform the destructive action at all.
    CANCEL = "cancel"


def confirm_unsaved_changes(
    parent: Optional[QWidget],
    dirty_count: int,
    *,
    title: str = "Unsaved changes",
    subject: str = "the current project",
    allow_save: bool = True,
) -> UnsavedChoice:
    """Ask what to do with ``dirty_count`` unsaved edits.

    Returns :attr:`UnsavedChoice.SAVE` when the user wants the edits kept,
    :attr:`UnsavedChoice.DISCARD` when they explicitly throw them away and
    :attr:`UnsavedChoice.CANCEL` when the destructive action must not happen
    at all.

    ``allow_save`` is ``False`` for actions that throw the *whole* project
    away (restoring the demo project): offering to save the edits there
    would be a lie, because the project is wiped either way.

    A count of zero or less needs no question, so the caller may simply
    proceed; the answer is then :attr:`UnsavedChoice.DISCARD` because there
    is nothing to save.
    """
    if dirty_count <= 0:
        return UnsavedChoice.DISCARD

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    if dirty_count == 1:
        box.setText("There is 1 unsaved edit.")
    else:
        box.setText(f"There are {dirty_count} unsaved edits.")

    save_button: Optional[QPushButton] = None
    if allow_save:
        box.setInformativeText(
            f"Save your changes to {subject} before continuing?"
        )
        save_button = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard_button = box.addButton(
            "Discard", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        if isinstance(save_button, QPushButton):
            box.setDefaultButton(save_button)
    else:
        box.setInformativeText(
            f"Continuing will permanently discard your changes to {subject}."
        )
        discard_button = box.addButton(
            "Discard changes", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(discard_button)

    box.exec()

    clicked = box.clickedButton()
    if save_button is not None and clicked is save_button:
        return UnsavedChoice.SAVE
    if clicked is discard_button:
        return UnsavedChoice.DISCARD
    return UnsavedChoice.CANCEL


def confirm_before_discard(
    parent: Optional[QWidget],
    context: "AppContext",
    *,
    action: str = "the current project",
    allow_save: bool = True,
) -> bool:
    """Ask before an action that would throw unsaved edits away.

    ``context`` is the shared :class:`~mmnext.ui.app_context.AppContext`.
    The count spans **every** working set, because a destructive action such
    as restoring the demo project discards narrator and exact-dubbing edits
    alike.

    Returns ``True`` when the caller may proceed. When the user picks
    *Save* the working sets are marked as saved first, so the destructive
    action starts from a clean state.
    """
    count = context.dirty.total_dirty()
    if count <= 0:
        return True

    choice = confirm_unsaved_changes(
        parent,
        count,
        title="Unsaved changes",
        subject=action,
        allow_save=allow_save,
    )
    if choice is UnsavedChoice.CANCEL:
        return False
    if choice is UnsavedChoice.SAVE:
        context.project.mark_narration_clean()
        context.project.mark_exact_rows_clean()
    return True
