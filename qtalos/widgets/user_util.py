from typing import Callable, TypeVar, Generic, Type, Union

from functools import partial

from qtalos.core import format_printer, regex_parser, PlaintextParseError, wrap_plaintext_parser, ValueWidget, \
    ValueWidgetTemplate, inner_plaintext_parser, ParseError

from qtalos.widgets.line import LineEdit
from qtalos.widgets.converter import ConverterWidget
from qtalos.widgets.confirmer import ConfirmValueWidget

T = TypeVar('T')


class SimpleEdit(Generic[T], ConverterWidget[str, T]):
    _func = inner_plaintext_parser(staticmethod(wrap_plaintext_parser(ValueError, partial(int, base=0))))
    MAKE_PLAINTEXT = MAKE_INDICATOR = False

    def __init__(self, title, **kwargs):
        line_edit_args = {}

        for k in ('placeholder',):
            if k in kwargs:
                line_edit_args[k] = kwargs[k]
                del kwargs[k]

        super().__init__(self.line_edit_cls.template(title, **line_edit_args), **kwargs)

    def back_convert(self, v: T):
        printer = self.joined_plaintext_printer
        return printer(v)

    def convert(self, v: str) -> T:
        parser = self.joined_plaintext_parser
        try:
            return parser(v)
        except PlaintextParseError as e:
            raise ParseError(...) from e

    line_edit_cls: Union[ValueWidgetTemplate[str], ValueWidget[str]] = LineEdit.template()

    _template_class = ValueWidget._template_class

    def template_of(self):
        return ValueWidget.template_of(self)

    def plaintext_parsers(self):
        return ValueWidget.plaintext_parsers(self)


class IntEdit(SimpleEdit[int]):
    def plaintext_printers(self):
        yield from super().plaintext_printers()
        yield hex
        yield bin
        yield oct
        yield format_printer('n')
        yield format_printer('X')


class FloatEdit(SimpleEdit[float]):
    _func = inner_plaintext_parser(staticmethod(wrap_plaintext_parser(ValueError, float)))

    @inner_plaintext_parser
    @staticmethod
    @regex_parser(r'([0-9]*(\.[0-9◘]+)?)%')
    def percentage(m):
        try:
            return float(m[1]) / 100
        except ValueError as e:
            raise PlaintextParseError(...) from e

    @inner_plaintext_parser
    @staticmethod
    @regex_parser(r'(?P<num>[0-9]+)\s*/\s*(?P<den>[1-9][0-9]*)')
    def ratio(m):
        n = m['num']
        d = m['den']

        try:
            n = float(n)
            d = float(d)
        except ValueError as e:
            raise PlaintextParseError(...) from e

        try:
            return n / d
        except ValueError as e:
            raise PlaintextParseError(...) from e

    def plaintext_printers(self):
        yield from super().plaintext_printers()
        yield format_printer('f')
        yield format_printer('e')
        yield format_printer('g')
        yield format_printer('%')


class ComplexEdit(SimpleEdit[complex]):
    _func = inner_plaintext_parser(staticmethod(wrap_plaintext_parser(ValueError, complex)))


def template(*args, **kwargs):
    def ret(c):
        return c.template(*args, **kwargs)

    return ret


if __name__ == '__main__':
    from qtalos.backend.QtWidgets import QApplication

    app = QApplication([])
    w = IntEdit('sample', make_plaintext=True, make_indicator=True)
    w.show()
    res = app.exec_()
    print(w.value())
    exit(res)
