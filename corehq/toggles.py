from toggle.shortcuts import toggle_enabled

class StaticToggle(object):
    def __init__(self, slug, label, namespaces=None):
        self.slug = slug
        self.label = label
        self.namespaces = namespaces or []

    def enabled(self, item, **kwargs):
        namespaces = [None] + self.namespaces
        return any([toggle_enabled(self.slug, item, namespace=n, **kwargs) for n in namespaces])
    

NAMESPACE_DOMAIN = 'domain'

APP_BUILDER_CUSTOM_PARENT_REF = StaticToggle(
    'custom-parent-ref',
    'Custom case parent reference'
)

APP_BUILDER_CAREPLAN = StaticToggle(
    'careplan',
    'Careplan module'
)

APP_BUILDER_ADVANCED = StaticToggle(
    'advanced-app-builder',
    'Advanced / CommTrack module'
)

APP_BUILDER_INCLUDE_MULTIMEDIA_ODK = StaticToggle(
    'include-multimedia-odk',
    'Include multimedia in ODK deploy'
)

PRBAC_DEMO = StaticToggle(
    'prbacdemo',
    'Roles and permissions'
)

ACCOUNTING_PREVIEW = StaticToggle(
    'accounting_preview',
    'Accounting preview',
    [NAMESPACE_DOMAIN]
)

OFFLINE_CLOUDCARE = StaticToggle(
    'offline-cloudcare',
    'Offline Cloudcare'
)

REMINDERS_UI_PREVIEW = StaticToggle(
    'reminders_ui_preview',
    'New reminders UI'
)

CALC_XPATHS = StaticToggle(
    'calc_xpaths',
    'Enabling custom calculated xpaths',
    namespaces=[NAMESPACE_DOMAIN],
)
