"""
Widgets « anti-defilement ».

Par defaut, les QSpinBox / QDoubleSpinBox / QComboBox capturent la molette (ou
le pave tactile) des qu'on les survole : le defilement de la page s'arrete et la
valeur change par inadvertance. Ces sous-classes ignorent l'evenement molette
tant que le widget n'a PAS le focus : le defilement se propage alors a la page.
Une fois clique (focus), la molette agit normalement sur le champ.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox


class _NoWheelMixin:
    def _init_no_wheel(self):
        # Empeche aussi la molette de donner le focus au champ.
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            # Ignore -> l'evenement remonte au parent (la zone defilante).
            event.ignore()


class NoScrollSpinBox(_NoWheelMixin, QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_no_wheel()


class NoScrollDoubleSpinBox(_NoWheelMixin, QDoubleSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_no_wheel()


class NoScrollComboBox(_NoWheelMixin, QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_no_wheel()
