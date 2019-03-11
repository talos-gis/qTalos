from __future__ import annotations

from typing import TypeVar, Generic, Iterable, Tuple, Union, Type, List, Dict

from collections import namedtuple
from functools import partial
from abc import abstractmethod
from itertools import chain

from qtalos.backend.QtWidgets import QVBoxLayout, QStackedWidget, QComboBox, QFrame, QRadioButton, QGroupBox, \
    QCheckBox, QBoxLayout

from qtalos.core import ValueWidget, ParseError, ValueWidgetTemplate
from qtalos.core.__util__ import first_valid

from qtalos.widgets.widget_wrappers import MultiWidgetWrapper
from qtalos.widgets.__util__ import only_valid

T = TypeVar('T')
NamedTemplate = Union[
    ValueWidgetTemplate[T], Tuple[str, ValueWidgetTemplate[T]],
    ValueWidget[T], Tuple[str, ValueWidget[T]]
]


class StackedValueWidget(Generic[T], MultiWidgetWrapper[T, T]):
    class Selector(ValueWidget[int]):
        MAKE_INDICATOR = MAKE_PLAINTEXT = MAKE_TITLE = False

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.options = {}

        @abstractmethod
        def add_option(self, name):
            index = len(self.options)
            if self.options.setdefault(name, index) != index:
                raise ValueError('duplicate name: ' + name)

        @abstractmethod
        def fill(self, index):
            if isinstance(index, str):
                self.fill(self.options[index])

    class ComboSelector(Selector):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.combo_box: QComboBox = None

            self.init_ui()

        def init_ui(self):
            layout = QVBoxLayout(self)
            self.combo_box = QComboBox()
            self.combo_box.currentIndexChanged.connect(self.change_value)
            layout.addWidget(self.combo_box)

        def parse(self):
            return self.combo_box.currentIndex()

        def add_option(self, name):
            self.combo_box.addItem(name)
            if self.combo_box.currentIndex() < 0:
                self.combo_box.setCurrentIndex(0)
            super().add_option(name)

        def fill(self, index):
            if isinstance(index, int):
                self.combo_box.setCurrentIndex(index)
            super().fill(index)

    class RadioSelector(Selector):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.group_box: QGroupBox = None
            self.layout: QVBoxLayout = None
            self.radio_buttons: List[QRadioButton] = None

            self.init_ui()

        def init_ui(self):
            layout = QVBoxLayout(self)
            self.group_box = QGroupBox()
            self.layout = QVBoxLayout(self.group_box)
            self.radio_buttons = []

            layout.addWidget(self.group_box)

        def parse(self):
            for i, rb in enumerate(self.radio_buttons):
                if rb.isChecked():
                    return i
            raise ParseError('no radio buttons')

        def add_option(self, name):
            rb = QRadioButton()
            rb.setText(name)
            self.layout.addWidget(rb)
            if not self.radio_buttons:
                rb.setChecked(True)
            self.radio_buttons.append(rb)
            rb.toggled.connect(self.change_value)
            super().add_option(name)

        def fill(self, index):
            if isinstance(index, int):
                self.radio_buttons[index].setChecked(True)
            super().fill(index)

    class CheckBoxSelector(Selector):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.check_box: QCheckBox = None

            self.value_count = 0

            self.init_ui()

        def init_ui(self):
            layout = QVBoxLayout(self)
            self.check_box = QCheckBox()
            self.check_box.toggled.connect(self.change_value)
            layout.addWidget(self.check_box)

        def parse(self):
            return int(self.check_box.isChecked())

        def add_option(self, name):
            if self.value_count >= 2:
                raise Exception('CheckBoxSelector can only contain 2 values')
            if self.value_count == 1:
                self.check_box.setText(name)
            else:
                self.check_box.setChecked(False)
            super().add_option(name)

        def fill(self, index):
            if isinstance(index, int):
                self.check_box.setChecked(bool(index))
            super().fill(index)

    selectors = {'combo': ComboSelector, 'radio': RadioSelector, 'checkbox': CheckBoxSelector}

    targeted_fill = namedtuple('targeted_fill', 'option_name value')

    def __init__(self, title, inner_templates: Iterable[NamedTemplate[T]] = None,
                 frame_style=None, selector_cls: Union[Type[Selector], str] = None,
                 layout_cls: Type[QBoxLayout] = None,
                 **kwargs):
        self.inner_templates = dict(
            self._to_name_subtemplate(o) for o in
            only_valid(inner_templates=inner_templates, INNER_TEMPLATES=self.INNER_TEMPLATES)
        )

        ValueWidgetTemplate.extract_default(*self.inner_templates.values(), sink=kwargs, upper_space=self, union=True)

        super().__init__(title, **kwargs)

        self.inners: Dict[str, ValueWidget[T]] = None

        self.selector: StackedValueWidget.Selector = None

        selector_cls = first_valid(selector_cls=selector_cls, SELECTOR_CLS=self.SELECTOR_CLS)
        if isinstance(selector_cls, str):
            selector_cls = self.selectors[selector_cls]
        self.selector_cls = selector_cls
        self.stacked: QStackedWidget = None

        self.init_ui(frame_style=frame_style, layout_cls=layout_cls)

    INNER_TEMPLATES: Iterable[NamedTemplate[T]] = None
    LAYOUT_CLS: Type[QBoxLayout] = QVBoxLayout
    SELECTOR_CLS: Union[Type[Selector], str] = 'combo'

    def init_ui(self, frame_style=None, layout_cls=None):
        super().init_ui()

        master_layout = QVBoxLayout(self)

        frame = QFrame()
        if frame_style is not None:
            frame.setFrameStyle(frame_style)

        layout_cls = first_valid(layout_cls=layout_cls, LAYOUT_CLS=self.LAYOUT_CLS)

        layout = layout_cls()

        with self.setup_provided(master_layout, layout):
            self.selector = self.selector_cls('select option')
            self.stacked = QStackedWidget()

            self.inners = {}
            for name, inner_template in self.inner_templates.items():
                inner: ValueWidget[T] = inner_template()
                if self.inners.setdefault(name, inner) is not inner:
                    raise TypeError(f'duplicate inner name: {name}')

                for p in chain(inner.provided_pre(),
                               inner.provided_post()):
                    p.hide()

                self.stacked.addWidget(inner)
                self.selector.add_option(name)

                inner.on_change.connect(self.change_value)

            self.selector.on_change.connect(self._selector_changed)
            layout.addWidget(self.selector)
            layout.addWidget(self.stacked)

        frame.setLayout(layout)
        master_layout.addWidget(frame)

    def parse(self):
        return self.current_subwidget().parse()

    def validate(self, v):
        return self.current_subwidget().validate(v)

    def plaintext_printers(self):
        return self.current_subwidget().plaintext_printers()

    def plaintext_parsers(self):
        def parser_wrap(option_name, parser, *args, **kwargs):
            return self.targeted_fill(option_name=option_name, value=parser(*args, **kwargs))

        current = self.current_subwidget()
        yield from current.plaintext_parsers()
        for n, o in self.inners.items():
            if o is current:
                continue
            for p in o.plaintext_parsers():
                new_parser = partial(parser_wrap, n, p)

                new_parser.__name__ = n + ': ' + p.__name__
                yield new_parser

    def current_subwidget(self) -> ValueWidget[T]:
        v: ValueWidget[T] = self.stacked.currentWidget()
        return v

    def fill(self, v: Union[T, targeted_fill]):
        if isinstance(v, self.targeted_fill):
            name = v.option_name
            v = v.value
            self.selector.fill(name)
        self.current_subwidget().fill(v)

    @staticmethod
    def _to_name_subtemplate(option: NamedTemplate) -> Tuple[str, ValueWidgetTemplate[T]]:
        try:
            template = option.template_of()
        except AttributeError:
            name, option = option
            option = option.template_of()
            return name, option

        if not template.title:
            raise ValueError(f'stacked option {option} must have a title')
        return template.title, template

    def _selector_changed(self):
        state, index, _ = self.selector.value()
        if not state.is_ok():
            raise index
        self.stacked.setCurrentIndex(index)
        self.change_value()


if __name__ == '__main__':
    from qtalos.backend import QApplication, QHBoxLayout

    from qtalos.widgets import ValueCheckBox, ValueCombo, IntEdit

    app = QApplication([])
    w = StackedValueWidget('number', [
        IntEdit('raw text', make_indicator=True),
        ValueCheckBox('sign', (0, 1)),
        ValueCombo('named', [('dozen', 12), ('one', 1), ('seven', 7)])
    ], make_plaintext=True, make_title=True, frame_style=QFrame.Box, selector_cls=StackedValueWidget.RadioSelector,
                           layout_cls=QHBoxLayout)
    w.show()
    res = app.exec_()
    print(w.value())
    exit(res)
