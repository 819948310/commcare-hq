from crispy_forms.helper import FormHelper
from crispy_forms import layout as crispy
from django import forms
from django.utils.translation import ugettext_lazy as _
from commcarehq.apps.sms.mixin import SMSBackend
from commcarehq.apps.sms.models import INCOMING, OUTGOING
from commcarehq.apps.sms.util import get_backend_by_class_name


class SMSRateCalculatorForm(forms.Form):
    gateway = forms.ChoiceField(label="Connection")
    country_code = forms.CharField(label="Country Code")
    direction = forms.ChoiceField(label="Direction", choices=(
        (OUTGOING, _("Outgoing")),
        (INCOMING, _("Incoming")),
    ))

    def __init__(self, domain, *args, **kwargs):
        super(SMSRateCalculatorForm, self).__init__(*args, **kwargs)

        backends = SMSBackend.view(
            "sms/backend_by_domain",
            startkey=[domain],
            endkey=[domain, {}],
            reduce=False,
            include_docs=True,
        ).all()
        backends.extend(SMSBackend.view(
            'sms/global_backends',
            reduce=False,
            include_docs=True,
        ).all())

        def _get_backend_info(backend):
            try:
                api_id = " (%s)" % get_backend_by_class_name(backend.doc_type).get_api_id()
            except AttributeError:
                api_id = ""
            return backend._id, "%s%s" % (backend.name, api_id)

        backends = [_get_backend_info(g) for g in backends]
        self.fields['gateway'].choices = backends

        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = crispy.Layout(
            crispy.Field(
                'gateway',
                data_bind="value: gateway, events: {change: clearSelect2}",
                css_class="input-xxlarge",
            ),
            crispy.Field(
                'direction', data_bind="value: direction, "
                                       "event: {change: clearSelect2}",
            ),
            crispy.Field(
                'country_code',
                css_class="input-xxlarge",
                data_bind="value: select2CountryCode.value, "
                          "event: {change: updateRate}",
                placeholder=_("Please Select a Country Code"),
            ),
        )
