from typing import Optional, Pattern, Union

import re

from qtalos.backend.QtWidgets import QLineEdit, QHBoxLayout

from qtalos.core import ValueWidget, inner_plaintext_parser, ValidationError

from qtalos.widgets.__util__ import optional_valid


class LineEdit(ValueWidget[str]):
    """
    A string ValueWidget, in the form of a QLineEdit
    """
    MAKE_INDICATOR = MAKE_TITLE = MAKE_PLAINTEXT = False
    PATTERN = None

    def __init__(self, title: str, pattern: Union[str, Pattern[str]] = None, placeholder=True,
                 **kwargs):
        """
        :param title: the title
        :param pattern: a regex pattern the value must match to be validated
        :param placeholder: whether to display the widget's title in a placeholder
        :param kwargs: forwarded to ValueWidget
        """
        super().__init__(title, **kwargs)

        pattern = optional_valid(pattern=pattern, PATTERN=self.PATTERN)

        self.pattern: Optional[Pattern[str]] = re.compile(pattern) if isinstance(pattern, str) else pattern

        self.edit: QLineEdit = None

        self.init_ui(placeholder=placeholder and self.title)

    def init_ui(self, placeholder=None):
        super().init_ui()
        layout = QHBoxLayout(self)

        with self.setup_provided(layout):
            self.edit = QLineEdit()
            if placeholder:
                self.edit.setPlaceholderText(placeholder)
            self.edit.textChanged.connect(self.change_value)

            layout.addWidget(self.edit)

    def parse(self):
        return self.edit.text()

    def validate(self, value):
        super().validate(value)
        if self.pattern and not self.pattern.fullmatch(value):
            raise ValidationError(f'value must match pattern {self.pattern}')

    @inner_plaintext_parser
    def raw_text(self, v):
        return v

    def fill(self, v: str):
        self.edit.setText(v)


if __name__ == '__main__':
    from qtalos.backend.QtWidgets import QApplication

    app = QApplication([])
    w = LineEdit('sample', pattern='(a[^a]*a|[^a])*', make_plaintext=True)
    w.show()
    res = app.exec_()
    print(w.value())
    exit(res)
