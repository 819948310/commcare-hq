from jsonobject import JsonObject, StringProperty, ListProperty, BooleanProperty, DictProperty
from jsonobject.exceptions import BadValueError
from commcarehq.apps.userreports.expressions.getters import TransformedGetter, getter_from_property_reference, \
    transform_from_datatype
from commcarehq.apps.userreports.operators import IN_MULTISELECT, EQUAL
from commcarehq.apps.userreports.specs import TypeProperty


DATA_TYPE_CHOICES = ['date', 'datetime', 'string', 'integer', 'decimal']


def DataTypeProperty(**kwargs):
    """
    Shortcut for valid data types.
    """
    return StringProperty(choices=DATA_TYPE_CHOICES, **kwargs)


class IndicatorSpecBase(JsonObject):
    """
    Base class for indicator specs. All specs (for now) are assumed to have a column_id and
    a display_name, which defaults to the column_id.
    """
    _allow_dynamic_properties = False

    type = StringProperty(required=True)

    column_id = StringProperty(required=True)
    display_name = StringProperty()

    @classmethod
    def wrap(cls, obj):
        wrapped = super(IndicatorSpecBase, cls).wrap(obj)
        if not wrapped.column_id:
            raise BadValueError('column_id must not be empty!')
        if not wrapped.display_name not in obj:
            wrapped.display_name = wrapped.column_id
        return wrapped


class PropertyReferenceIndicatorSpecBase(IndicatorSpecBase):
    """
    Extension of an indicator spec that references a property - either via
    a property_name or property_path.
    """
    property_name = StringProperty()
    property_path = ListProperty()

    @property
    def getter(self):
        return getter_from_property_reference(self)


class BooleanIndicatorSpec(IndicatorSpecBase):
    type = TypeProperty('boolean')
    filter = DictProperty(required=True)


class RawIndicatorSpec(PropertyReferenceIndicatorSpecBase):
    type = TypeProperty('raw')
    datatype = DataTypeProperty(required=True)
    is_nullable = BooleanProperty(default=True)
    is_primary_key = BooleanProperty(default=False)

    @property
    def getter(self):
        transform = transform_from_datatype(self.datatype)
        getter = getter_from_property_reference(self)
        return TransformedGetter(getter, transform)


class ExpressionIndicatorSpec(IndicatorSpecBase):
    type = TypeProperty('expression')
    datatype = DataTypeProperty(required=True)
    is_nullable = BooleanProperty(default=True)
    is_primary_key = BooleanProperty(default=False)
    expression = DictProperty(required=True)

    def parsed_expression(self, context):
        from commcarehq.apps.userreports.expressions.factory import ExpressionFactory
        transform = transform_from_datatype(self.datatype)
        expression = ExpressionFactory.from_spec(self.expression, context)
        return TransformedGetter(expression, transform)


class ChoiceListIndicatorSpec(PropertyReferenceIndicatorSpecBase):
    type = TypeProperty('choice_list')
    choices = ListProperty(required=True)
    select_style = StringProperty(choices=['single', 'multiple'])

    def get_operator(self):
        return IN_MULTISELECT if self.select_style == 'multiple' else EQUAL
