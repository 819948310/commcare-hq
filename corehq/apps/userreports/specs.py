from jsonobject import JsonObject, StringProperty, ListProperty, BooleanProperty, DictProperty

# todo: all spec definitions will go here. moving them over piece meal when touched.
from jsonobject.exceptions import BadValueError
from corehq.apps.userreports.getters import DictGetter, NestedDictGetter
from corehq.apps.userreports.logic import IN_MULTISELECT, EQUAL


class IndicatorSpecBase(JsonObject):
    """
    Base class for indicator specs. All specs (for now) are assumed to have a column_id and
    a display_name, which defaults to the column_id.
    """
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
        return _getter_from_property_reference(self)


class BooleanIndicatorSpec(IndicatorSpecBase):
    filter = DictProperty(required=True)


class RawIndicatorSpec(PropertyReferenceIndicatorSpecBase):
    datatype = StringProperty(required=True,
                              choices=['date', 'string', 'integer'])
    is_nullable = BooleanProperty(default=True)
    is_primary_key = BooleanProperty(default=False)


class ChoiceListIndicatorSpec(PropertyReferenceIndicatorSpecBase):
    choices = ListProperty(required=True)
    select_style = StringProperty()

    def get_operator(self):
        return IN_MULTISELECT if self.select_style == 'multiple' else EQUAL



class PropertyMatchFilterSpec(JsonObject):
    property_name = StringProperty()
    property_path = ListProperty()
    property_value = StringProperty(required=True)

    @property
    def getter(self):
        return _getter_from_property_reference(self)


def _getter_from_property_reference(spec):
    if spec.property_name:
        assert not spec.property_path
        return DictGetter(property_name=spec.property_name)
    else:
        assert spec.property_path
        return NestedDictGetter(property_path=spec.property_path)
