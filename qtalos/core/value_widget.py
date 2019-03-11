from __future__ import annotations

from typing import Generic, TypeVar, Optional, Callable, Tuple, Iterable, Type, Dict, Any

from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from functools import partial, wraps
from itertools import chain

from qtalos.backend.QtWidgets import QWidget, QPlainTextEdit, QPushButton, QComboBox, QLabel, QHBoxLayout, QVBoxLayout, \
    QMessageBox, QFileDialog, QGroupBox, QGridLayout
from qtalos.backend.QtCore import Qt, pyqtSignal, __backend__

from qtalos.core.plaintext_adapter import PlaintextParseError, PlaintextPrintError, \
    join_parsers, join_printers, PlaintextParser, PlaintextPrinter
from qtalos.core.parsed_value import ParsedValue, ParseError, ValidationError
from qtalos.core.__util__ import error_details, error_tooltip, first_valid

T = TypeVar('T')


# todo document this bullcrap


class ValueWidgetTemplate(Generic[T]):
    """
    A template for a ValueWidget
    """

    def __init__(self, widget_cls: Type[ValueWidget[T]], args: Tuple, kwargs: Dict[str, Any]):
        """
        :param widget_cls: the class of the ValueWidget
        :param args: the positional arguments of the template
        :param kwargs: the keyword arguments of the template
        """
        self.widget_cls = widget_cls
        self.args = args
        self.kwargs = kwargs

    @property
    def title(self) -> Optional[str]:
        """
        The title of the template, or None if one has not been provided
        """
        if self.args:
            ret = self.args[0]
            if not isinstance(ret, str):
                raise TypeError('first parameter of a template must be the title string')
            return ret
        else:
            return None

    def _partial(self):
        return partial(self.widget_cls, *self.args, **self.kwargs)

    def __call__(self, *args, **kwargs) -> ValueWidget[T]:
        """
        Create a widget form the template. args and kwargs are forwarded to the class constructor.
        """
        return self._partial()(*args, **kwargs)

    def template(self, *args, **kwargs):
        """
        Create a further template from additional parameters
        """
        args = self.args + args
        kwargs = {**self.kwargs, **kwargs}
        return type(self)(self.widget_cls, args, kwargs)

    def template_of(self):
        """
        return a template representing this template
        """
        return self

    def extract_default(*templates: ValueWidgetTemplate, sink: dict, upper_space, keys: Iterable[str] = ...,
                        union=True):
        """
        inject the default values from a template or collection of templates as defaults for keyword arguments.

        :param templates: A tuple of templates to extract from
        :param sink: the dict to set defaults for
        :param upper_space: a namespace, if a key exists in uppercase in that namespace as not None, the key is not
            filled into sink.
        :param keys: a list of keys to extract
        :param union: whether to perform a union or intersect in case of multiple, conflicting default values
        """

        def combine_key(k):
            ret = None
            for t in templates:
                v = t.kwargs.get(k)
                if v is None:
                    v = getattr(t.widget_cls, k.upper(), None)
                if v is not None:
                    if v == union:
                        return union
                    else:
                        ret = v
            return ret

        if keys is ...:
            keys = ('make_plaintext', 'make_indicator', 'make_title', 'auto_func')

        for k in keys:
            if k in sink or getattr(upper_space, k.upper(), None) is not None:
                continue
            v = combine_key(k)
            if v is not None:
                sink[k] = v

    def __repr__(self):
        params = ', '.join(chain(
            (repr(a) for a in self.args),
            (k + '=' + repr(v) for k, v in self.kwargs.items())
        ))
        return f'{self.widget_cls.__name__}.template({params})'


class ValueWidget(QWidget, Generic[T]):
    """
    A QWidget that can contain a value, parsed form its children widgets.
    """
    # todo fast/slow validation/parse? does confirmed already handle this?
    on_change = pyqtSignal()

    # region inherit_me
    """
    How do I inherit ValueWidget?
    * MAKE_TITLE, MAKE_INDICATOR, MAKE_PLAINTEXT, set these for true or false to implement default values.
    * __init__: Call super().__init__ and all's good.
        Don't fill validation_func or auto_func here, instead re-implement validate.
        At the end of your __init__, call init_ui **only if your class isn't going to be subclassed**.
    * init_ui: initialize all the widgets here. call super().init_ui.
        If you intend your class to be subclassed, don't add any widgets to self.
        if you want to add the provided widgets (see below), always do it in an if clause,
            since all provided widgets can be None.
        connect all widgets that change the outcome of parse to self's change_value slot.
        Provided Widgets:
        * title_label: a label that only contains the title of the widget.
            If help is provided, the label displays the help when clicked.
        * validation_label: a label that reads OK or ERR, depending on whether the value is parsed/valid.
        * plaintext_button: a button that allows raw plaintext reading and writing of the value.
        * auto_button: a button to automatically fill the widget's value according to external widgets.
    * validate: call super().validate(value) (it will call validate_func, if provided).
        You can raise ValidationError if the value is invalid.
    * parse: implement, convert the data on the widgets to a value, or raise ParseError.
    * plaintext_printers: yield from super().plaintext_printer, and yield whatever printers you want.
    * plaintext_parsers: yield from super().plaintext_parsers (empty by default), and yield whatever parsers you want.
        * NOTE: you can also just wrap class function with InnerParser / InnerPrinter
    * fill: optional, set the widget's values based on a value
    """
    MAKE_TITLE: bool = None
    MAKE_INDICATOR: bool = None
    MAKE_PLAINTEXT: bool = None

    def __new__(cls, *args, **kwargs):
        ret = super().__new__(cls, *args, **kwargs)
        ret.__new_args = (args, kwargs)
        return ret

    def __init__(self, title,
                 *args,
                 validation_func: Callable[[T], None] = None,
                 auto_func: Callable[[], T] = None,
                 make_title: bool = None,
                 make_indicator: bool = None,
                 make_plaintext: bool = None,
                 help: str = None,
                 **kwargs):
        """
        :param title: the title of the ValueWidget
        :param args: additional arguments forwarded to QWidget
        :param validation_func: a validation callable, that will raise ValidationError if the parsed value is invalid
        :param auto_func: a function that returns an automatic value, to fill in the UI
        :param make_title: whether to create a title widget
        :param make_indicator: whether to make an indicator widget
        :param make_plaintext: whether to make a plaintext_edit widget
        :param help: a help string to describe the widget
        :param kwargs: additional arguments forwarded to QWidget

        :inheritors: don't set default values for these parameters, change the uppercase class variables instead.
        """
        if kwargs.get('flags', ()) is None:
            kwargs['flags'] = Qt.WindowFlags()

        if 'flags' in kwargs and __backend__.__name__ == 'PySide2':
            kwargs['f'] = kwargs.pop('flags')

        try:
            super().__init__(*args, **kwargs)
        except (TypeError, AttributeError):
            print(f'args: {args}, kwargs: {kwargs}')
            raise
        self.title = title
        self.help = help

        self.make_title = first_valid(make_title=make_title, MAKE_TITLE=self.MAKE_TITLE)
        self.make_indicator = first_valid(make_indicator=make_indicator, MAKE_INDICATOR=self.MAKE_INDICATOR)
        self.make_plaintext = first_valid(make_plaintext=make_plaintext, MAKE_PLAINTEXT=self.MAKE_PLAINTEXT)

        self.indicator_label: Optional[QLabel] = None
        self.auto_button: Optional[QPushButton] = None
        self.plaintext_button: Optional[QPushButton] = None
        self.title_label: Optional[QLabel] = None

        self._plaintext_widget: Optional[PlaintextEditWidget[T]] = None

        self.validation_func = validation_func
        self.auto_func = auto_func

        self._suppress_update = False

        self._value: ParsedValue[T] = None
        self._joined_plaintext_printer = None
        self._joined_plaintext_parser = None

        if self.auto_func:
            if self.fill is None:
                raise Exception('auto_func can only be used on a ValueWidget with an implemented fill method')
            else:
                self.make_auto = True
        else:
            self.make_auto = False

    def init_ui(self):
        """
        initialise the internal widgets of the valuewidget
        :inheritors: If you intend your class to be subclassed, don't add any widgets to self.
        """
        # todo split init_ui into two functions: one to build, one to construct
        self.setWindowTitle(self.title)

        if self.make_indicator:
            self.indicator_label = QLabel('')
            self.indicator_label.mousePressEvent = self._detail_button_clicked

        if self.make_auto:
            self.auto_button = QPushButton('auto')
            self.auto_button.clicked.connect(self._auto_btn_click)

        if self.make_plaintext:
            self.plaintext_button = QPushButton('text')
            self.plaintext_button.clicked.connect(self._plaintext_btn_click)

            self._plaintext_widget = PlaintextEditWidget(parent=self, flags=Qt.Dialog)

        if self.make_title:
            self.title_label = QLabel(self.title)
            if self.help:
                self.title_label.mousePressEvent = self._help_clicked

    # implement this method to allow the widget to be filled from outer elements (like plaintext or auto)
    fill: Optional[Callable[[ValueWidget[T], T], None]] = None

    @abstractmethod
    def parse(self) -> T:
        """
        Parse the internal UI and returned a parsed value. Or raise ParseException.
        :return: the parsed value
        """
        pass

    def validate(self, value: T) -> None:
        """
        Raise a ValidationError if the value is invalid
        :param value: the parsed value
        :inheritors: always call super().validate
        """
        if self.validation_func:
            self.validation_func(value)

    def plaintext_printers(self) -> Iterable[PlaintextPrinter[T]]:
        """
        :return: an iterator of plaintext printers for the widget
        """
        yield from self._inner_plaintext_printers()
        yield str
        yield repr

    def plaintext_parsers(self) -> Iterable[PlaintextParser[T]]:
        """
        :return: an iterator of plaintext parsers for the widget
        """
        yield from self._inner_plaintext_parsers()

    # endregion

    # region call_me
    @contextmanager
    def suppress_update(self, new_value=True, call_on_exit=True):
        """
        A context manager, while called, will suppress updates to the indicator. will update the indicator when exited.
        """
        prev_value = self._suppress_update
        self._suppress_update = new_value
        yield new_value
        self._suppress_update = prev_value
        if call_on_exit:
            self.change_value()

    @property
    def joined_plaintext_parser(self):
        """
        :return: A joining of the widget's plaintext parsers
        """
        if not self._joined_plaintext_parser:
            self._joined_plaintext_parser = join_parsers(self.plaintext_parsers)
        return self._joined_plaintext_parser

    @property
    def joined_plaintext_printer(self):
        """
        :return: A joining of the widget's plaintext printers
        """
        if not self._joined_plaintext_printer:
            self._joined_plaintext_printer = join_printers(self.plaintext_printers)
        return self._joined_plaintext_printer

    def provided_pre(self, exclude=()):
        """
        Get an iterator of the widget's provided widgets that are to appear before the main UI.
        :param exclude: whatever widgets to exclude
        """
        return (yield from (
            y for y in (self.title_label,)
            if y and y not in exclude
        ))

    def provided_post(self, exclude=()):
        """
        Get an iterator of the widget's provided widgets that are to appear after the main UI.
        :param exclude: whatever widgets to exclude
        """
        return (yield from (
            y for y in (self.indicator_label,
                        self.auto_button,
                        self.plaintext_button)
            if y and y not in exclude
        ))

    @contextmanager
    def setup_provided(self, pre_layout: QVBoxLayout, post_layout=..., exclude=()):
        """
        a context manager that will add the pre_provided widgets before the block and the post_provided after it.
        :param pre_layout: a layout to add the pre_provided to
        :param post_layout: a layout to add teh post_provided to, default is to use pre_layout
        :param exclude: which provided widgets to exclude
        """
        for p in self.provided_pre(exclude=exclude):
            pre_layout.addWidget(p)
        yield
        if post_layout is ...:
            post_layout = pre_layout
        for p in self.provided_post(exclude=exclude):
            post_layout.addWidget(p)

        self._update_indicator()

    # endregion

    # region call_me_from_outside
    def fill_from_text(self, s: str):
        """
        fill the UI from a string, by parsing it
        :param s: the string to parse
        """
        if not self.fill:
            raise Exception(f'widget {self} does not have its fill function implemented')
        return self.fill(self.joined_plaintext_parser(s))

    def value(self) -> ParsedValue[T]:
        """
        :return: the current value of the widget
        """
        if self._value is None:
            self._reload_value()
        return self._value

    def change_value(self, *args):
        """
        a slot to refresh the value of the widget
        """
        self._invalidate_value()
        self._update_indicator()
        self.on_change.emit()

    _template_class: Type[ValueWidgetTemplate[T]] = ValueWidgetTemplate

    @classmethod
    @wraps(__init__)
    def template(cls, *args, **kwargs) -> ValueWidgetTemplate[T]:
        """
        get a template of the type
        :param args: arguments for the template
        :param kwargs: keyword arguments for the template
        :return: the template
        """
        return cls._template_class(cls, args, kwargs)

    def template_of(self) -> ValueWidgetTemplate[T]:
        """
        get a template to recreate the widget
        """
        a, k = self.__new_args
        ret = self.template(*a, **k)
        return ret

    @classmethod
    def template_class(cls, class_):
        """
        Assign a class to be this widget class's template class
        """
        cls._template_class = class_
        return class_

    def __str__(self):
        return super().__str__() + ': ' + self.title

    # endregion

    def _invalidate_value(self):
        """
        Mark the cached value is invalid, forcing it to be re-processed when needed next
        """
        self._value = None

    def _auto_btn_click(self, click_args):
        """
        autofill the widget
        """
        try:
            value = self.auto_func()
        except DoNotFill as e:
            if str(e):
                QMessageBox.critical(self, 'error during autofill', str(e))
            return

        with self.suppress_update():
            self.fill(value)

    def _plaintext_btn_click(self):
        """
        open the plaintext dialog
        """
        self._plaintext_widget.prep_for_show()
        self._plaintext_widget.show()

    def _update_indicator(self, *args):
        """
        update whatever indicators need updating when the value is changed
        """
        if self._suppress_update:
            return

        parsed = self.value()

        if self.indicator_label and self.indicator_label.parent():
            if parsed.is_ok():
                text = 'OK'
                tooltip = str(parsed.value)
            else:
                text = 'ERR'
                tooltip = error_tooltip(parsed.value)

            self.indicator_label.setText(text)
            self.indicator_label.setToolTip(tooltip)

        if self.plaintext_button and self.plaintext_button.parent():
            self.plaintext_button.setEnabled(parsed.is_ok() or any(self.plaintext_parsers()))

    def _reload_value(self):
        """
        reload the cached value
        """
        assert self._value is None, '_reload called when a value is cached'
        try:
            value = self.parse()
            self.validate(value)
        except (ValidationError, ParseError) as e:
            self._value = ParsedValue.from_error(e)
            return

        try:
            details = self.joined_plaintext_printer(value)
        except PlaintextPrintError as e:
            details = 'details could not be loaded because of a parser error:\n' + error_details(e)

        self._value = ParsedValue.from_value(value, details)

    def _detail_button_clicked(self, event):
        """
        show details of the value
        """
        if self._value.details:
            QMessageBox.information(self, 'validation details', self._value.details)

    def _help_clicked(self, event):
        """
        show help message
        """
        if self.help:
            QMessageBox.information(self, self.title, self.help)

    @staticmethod
    def _inner_plaintext_parsers():
        """
        get the inner plaintext parsers
        """
        yield from ()

    @staticmethod
    def _inner_plaintext_printers():
        """
        get the inner plaintext printers
        """
        yield from ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.on_change = pyqtSignal()

        inner_printers = []
        inner_parsers = []
        for v in cls.__dict__.values():
            if getattr(v, '__plaintext_printer__', False):
                inner_printers.append(v)
            if getattr(v, '__plaintext_parser__', False):
                inner_parsers.append(v)

        if inner_printers:
            def inner_printers_func(self):
                yield from (p.__get__(self, type(self)) for p in inner_printers)

            cls._inner_plaintext_printers = inner_printers_func

        if inner_parsers:
            def inner_parsers_func(self):
                yield from (p.__get__(self, type(self)) for p in inner_parsers)

            cls._inner_plaintext_parsers = inner_parsers_func


class DoNotFill(Exception):
    """
    if this exception is raised from an auto_func, a value is not filled in.
    """
    pass


class PlaintextEditWidget(Generic[T], ValueWidget[T]):
    """
    plaintext dialog for a ValueWidget
    """

    class _ShiftEnterIgnoringPlainTextEdit(QPlainTextEdit):
        """
        A QPlainTextEdit that ignores shift+enter
        """

        def keyPressEvent(self, event):
            if (event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Return) \
                    or (event.modifiers() == Qt.KeypadModifier | Qt.ShiftModifier and event.key() == Qt.Key_Enter):
                event.ignore()
            else:
                return super().keyPressEvent(event)

    NO_CURRENT_VALUE = object()

    MAKE_INDICATOR = True
    MAKE_PLAINTEXT = False
    MAKE_TITLE = False

    def __init__(self, *args, **kwargs):
        super().__init__('plaintext edit', *args, **kwargs)

        self.current_value: T = self.NO_CURRENT_VALUE

        self.print_widget: QWidget = None
        self.print_edit: QPlainTextEdit = None
        self.print_combo: QComboBox = None
        self.ok_button: QPushButton = None
        self.apply_button: QPushButton = None

        self.parse_widget: QWidget = None
        self.parse_edit: PlaintextEditWidget._ShiftEnterIgnoringPlainTextEdit = None
        self.parse_combo: QComboBox = None

        self.owner: Optional[ValueWidget[T]] = None

        self.init_ui()

    def init_ui(self):
        super().init_ui()
        self.setWindowModality(Qt.WindowModal)

        master_layout = QVBoxLayout(self)

        self.print_widget = QGroupBox('current value:')
        print_master_layout = QVBoxLayout(self.print_widget)

        print_layout = QHBoxLayout()
        print_master_layout.addLayout(print_layout)

        self.print_edit = QPlainTextEdit()
        self.print_edit.setReadOnly(True)
        print_layout.addWidget(self.print_edit)

        print_extras_layout = QGridLayout()

        self.print_combo = QComboBox()
        file_button = QPushButton('to file...')
        file_button.clicked.connect(self.save_file)
        print_extras_layout.addWidget(file_button, 0, 0)
        print_extras_layout.addWidget(self.print_combo, 1, 0)

        print_layout.addLayout(print_extras_layout)

        master_layout.addWidget(self.print_widget)

        self.parse_widget = QGroupBox('set value:')
        parse_master_layout = QVBoxLayout(self.parse_widget)

        parse_layout = QHBoxLayout()
        parse_master_layout.addLayout(parse_layout)

        self.parse_edit = self._ShiftEnterIgnoringPlainTextEdit()
        self.parse_edit.textChanged.connect(self.change_value)
        self.print_combo.currentIndexChanged[int].connect(self.update_print)
        parse_layout.addWidget(self.parse_edit)

        parse_extras_layout = QGridLayout()

        self.parse_combo = QComboBox()
        self.parse_combo.currentIndexChanged[int].connect(self.change_value)
        parse_extras_layout.addWidget(self.parse_combo, 0, 0)

        if self.indicator_label:
            parse_extras_layout.addWidget(self.indicator_label, 0, 1)

        file_button = QPushButton('from file...')
        file_button.clicked.connect(self.load_file)
        parse_extras_layout.addWidget(file_button, 1, 0, 1, 2)

        self.apply_button = QPushButton('apply')
        self.apply_button.clicked.connect(self.apply_parse)
        parse_extras_layout.addWidget(self.apply_button, 2, 0)

        self.ok_button = QPushButton('OK')
        self.ok_button.clicked.connect(self.commit_parse)
        parse_extras_layout.addWidget(self.ok_button, 2, 1)

        parse_layout.addLayout(parse_extras_layout)

        master_layout.addWidget(self.parse_widget)

        self.on_change.connect(self._on_value_change)

    def parse(self):
        parser: PlaintextParser = self.parse_combo.currentData()
        if not parser:
            raise ParseError('no parser configured')

        try:
            return parser(self.parse_edit.toPlainText())
        except PlaintextParseError as e:
            raise ParseError(...) from e

    def load_file(self, *args):
        filename, _ = QFileDialog.getOpenFileName(self, 'open file', filter='text files (*.txt *.csv);;all files (*.*)')
        if not filename:
            return

        try:
            text = Path(filename).read_text()
        except IOError as e:
            QMessageBox.critical(self, 'could not read file', str(e))
        else:
            self.parse_edit.setPlainText(text)

    def save_file(self, *args):
        filename, _ = QFileDialog.getSaveFileName(self, 'save file', filter='text files (*.txt *.csv);;all files (*.*)')
        if not filename:
            return

        try:
            Path(filename).write_text(self.print_edit.toPlainText())
        except IOError as e:
            QMessageBox.critical(self, 'could not write to file', str(e))

    def update_print(self, *args):
        if self.current_value is self.NO_CURRENT_VALUE:
            text = '<no current value>'
        else:
            printer: PlaintextPrinter = self.print_combo.currentData()
            if not printer:
                text = '<no printer configured>'
            else:
                try:
                    text = printer(self.current_value)
                except PlaintextPrintError as e:
                    text = f'<printer error: {e}>'

        self.print_edit.setPlainText(text)

    def prep_for_show(self, clear_parse=True, clear_print=True):
        """
        prepare a dialog with a new owner and value.
        :param clear_parse: whether to clear and reset the parse UI
        :param clear_print: whether to clear and reset the print UI
        """

        self.setWindowTitle('plaintext edit for ' + self.owner.title)

        owner_value = self.owner.value()
        if not owner_value.is_ok():
            self.print_widget.setVisible(False)
            printers = False
        else:
            self.current_value = owner_value.value

            self.print_widget.setVisible(True)
            printers = list(self.owner.plaintext_printers())
            # setup the print

            combo_index = 0
            if clear_print:
                pass
            else:
                combo_index = self.print_combo.currentIndex()
                if combo_index == -1:
                    combo_index = 0

            self.print_combo.clear()
            if len(printers) > 1:
                self.print_combo.setVisible(True)
                self.print_combo.addItem('<all>', self.owner.joined_plaintext_printer)
            else:
                self.print_combo.setVisible(False)

            for printer in printers:
                name = printer.__name__
                if getattr(printer, '__explicit__', False):
                    name += '*'
                self.print_combo.addItem(name, printer)

            self.print_combo.setCurrentIndex(combo_index)

        parsers = list(self.owner.plaintext_parsers())
        if not parsers:
            self.parse_widget.setVisible(False)
        else:
            if not self.owner.fill:
                raise Exception(
                    f'parsers are defined but the widget has no implemented fill method (in widget {self.owner})')

            self.parse_widget.setVisible(True)
            combo_index = 0

            if clear_parse:
                self.parse_edit.clear()
            else:
                combo_index = self.parse_combo.currentIndex()
                if combo_index == -1:
                    combo_index = 0

            self.parse_combo.clear()
            if len(parsers) > 1:
                self.parse_combo.setVisible(True)
                self.parse_combo.addItem('<all>', self.owner.joined_plaintext_parser)
            else:
                self.parse_combo.setVisible(False)

            for parser in parsers:
                name = parser.__name__
                if getattr(parser, '__explicit__', False):
                    name += '*'
                self.parse_combo.addItem(name, parser)
            self.parse_combo.setCurrentIndex(combo_index)

        if not printers and not parsers:
            raise ValueError('plaintext edit widget prepped for owner without any plaintext adapters')

    def commit_parse(self):
        parsed = self.value()
        if not parsed.is_ok():
            QMessageBox.critical(self, 'error parsing plaintext', error_details(self.result_value))
        else:
            self.owner.fill(parsed.value)
            self.close()

    def apply_parse(self):
        parsed = self.value()
        if not parsed.is_ok():
            QMessageBox.critical(self, 'error parsing plaintext', error_details(self.result_value))
        else:
            self.owner.fill(parsed.value)
            self.prep_for_show(clear_parse=False, clear_print=False)
            self.parse_edit.setFocus()

    @property
    def has_parse(self):
        return bool(self.parsers)

    @property
    def has_print(self):
        return bool(self.printers)

    def _on_value_change(self, *a):
        state = self.value().value_state

        self.ok_button.setEnabled(state.is_ok())
        self.apply_button.setEnabled(state.is_ok())

    def keyPressEvent(self, event):
        if (event.modifiers() == Qt.ShiftModifier and event.key() == Qt.Key_Return) \
                or (event.modifiers() == Qt.KeypadModifier | Qt.ShiftModifier and event.key() == Qt.Key_Enter):
            self.ok_button.click()
        elif not event.modifiers() and event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
