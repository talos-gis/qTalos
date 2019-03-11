from typing import TypeVar, Generic, Iterable

from qtalos.core import ValueWidget, ValueWidgetTemplate

from qtalos.widgets.idiomatic_inner import get_idiomatic_inner_template

T = TypeVar('T')
I = TypeVar('I')


class SingleWidgetWrapper(Generic[I, T], ValueWidget[T]):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        idiomatic_inners = get_idiomatic_inner_template(cls)
        try:
            inner_template = next(idiomatic_inners)
        except StopIteration:
            inner_template = None
        else:
            if cls.INNER_TEMPLATE:
                raise Exception('cannot define idiomatic inner template inside a class with an INNER_TEMPLATE')
            try:
                _ = next(idiomatic_inners)
            except StopIteration:
                pass
            else:
                raise Exception(f'{cls.__name__} can only have 1 idiomatic inner template')

        if inner_template:
            cls.INNER_TEMPLATE = inner_template

    INNER_TEMPLATE: ValueWidgetTemplate[T]


class MultiWidgetWrapper(Generic[I, T], ValueWidget[T]):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        idiomatic_inners = list(get_idiomatic_inner_template(cls))
        if idiomatic_inners:
            if cls.INNER_TEMPLATES:
                raise Exception('cannot define idiomatic inner templates inside a class with an INNER_TEMPLATES')

            cls.INNER_TEMPLATES = idiomatic_inners

    INNER_TEMPLATES: Iterable[ValueWidgetTemplate[I]] = None
