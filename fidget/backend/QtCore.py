from __future__ import annotations

from typing import TYPE_CHECKING, Type

from fidget.backend import load

if TYPE_CHECKING:
    import PyQt5.QtCore

__backend__ = load()

_QtCore = __backend__.partial('QtCore')

QEvent: Type[PyQt5.QtCore.QEvent] = _QtCore['QEvent']
QObject: Type[PyQt5.QtCore.QObject] = _QtCore['QObject']
Qt: Type[PyQt5.QtCore.Qt] = _QtCore['Qt']
pyqtSignal: Type[PyQt5.QtCore.pyqtSignal] = _QtCore['pyqtSignal']


def __getattr__(name):
    return _QtCore[name]