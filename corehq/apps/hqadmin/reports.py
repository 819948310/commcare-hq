import copy
from datetime import datetime
import json
from corehq import Domain
from corehq.apps.accounting.models import (
    SoftwarePlanEdition,
    Subscription,
)
from corehq.apps.app_manager.models import Application
from corehq.apps.reports.datatables import DataTablesHeader, DataTablesColumn
from corehq.apps.reports.dispatcher import AdminReportDispatcher
from corehq.apps.reports.generic import ElasticTabularReport, GenericTabularReport
from django.utils.translation import ugettext as _, ugettext_noop
from corehq.apps.users.models import WebUser
from corehq.elastic import es_query, parse_args_for_es, fill_mapping_with_facets
from corehq.pillows.mappings.app_mapping import APP_INDEX
from corehq.pillows.mappings.user_mapping import USER_INDEX
from corehq.apps.app_manager.commcare_settings import SETTINGS as CC_SETTINGS
from corehq.toggles import IS_DEVELOPER


INDICATOR_DATA = {
    "domain_count": {
        "ajax_view": "admin_reports_stats_data",
        "chart_name": "domains",
        "chart_title": "Total Project Spaces",
        "date_field_opts": [
            {
                "name": "Date Created",
                "value": "date_created",
            },
        ],
        "histogram_type": "domains",
        "interval": "week",
        "xaxis_label": "# domains",
    },
    "domain_self_started_count": {
        "ajax_view": "admin_reports_stats_data",
        "chart_name": "self_started_domains",
        "chart_title": "Self-Started Project Spaces",
        "date_field_opts": [
            {
                "name": "Date Created",
                "value": "date_created",
            },
        ],
        "params_es_dict": {
            "internal.self_started": ["T"],
        },
        "histogram_type": "domains",
        "interval": "week",
        "xaxis_label": "# domains",
    },
    "forms": {
        "ajax_view": "admin_reports_stats_data",
        "chart_name": "forms",
        "chart_title": "All Forms",
        "histogram_type": "forms",
        "interval": "week",
        "xaxis_label": "# forms",
    },
    "forms_mobile": {
        "ajax_view": "admin_reports_stats_data",
        "chart_name": "forms_mobile",
        "chart_title": "Forms Submitted by Mobile Workers",
        "histogram_type": "forms",
        "interval": "week",
        "params_es_dict": {
            "user_type_mobile": True,
        },
        "xaxis_label": "# forms",
    },
    "forms_web": {
        "ajax_view": "admin_reports_stats_data",
        "chart_name": "forms_web",
        "chart_title": "Forms Submitted by Web Users",
        "histogram_type": "forms",
        "interval": "week",
        "params_es_dict": {
            "user_type_mobile": False,
        },
        "xaxis_label": "# forms",
    },
    "users": {
        "ajax_view": "admin_reports_stats_data",
        "chart_name": "users",
        "chart_title": "Total Users",
        "histogram_type": "users",
        "interval": "week",
        "xaxis_label": "# users",
    },
    "users_mobile": {
        "ajax_view": "admin_reports_stats_data",
        "chart_name": "users_mobile",
        "chart_title": "Mobile Users (submitted)",
        "histogram_type": "users",
        "interval": "week",
        "params_es_dict": {
            "user_type_mobile": True,
        },
        "xaxis_label": "# users",
    },
    "users_web": {
        "ajax_view": "admin_reports_stats_data",
        "chart_name": "users_web",
        "chart_title": "Web Users (submitted)",
        "histogram_type": "users",
        "interval": "week",
        "params_es_dict": {
            "user_type_mobile": False,
        },
        "xaxis_label": "# users",
    },
}


class AdminReport(GenericTabularReport):
    dispatcher = AdminReportDispatcher
    base_template = "hqadmin/faceted_report.html"

class AdminFacetedReport(AdminReport, ElasticTabularReport):
    default_sort = None
    es_prefix = "es_" # facet keywords in the url will be prefixed with this
    asynchronous = False
    ajax_pagination = True
    exportable = True
    es_queried = False
    es_facet_list = []
    es_facet_mapping = []
    section_name = ugettext_noop("ADMINREPORT")
    es_url = ''

    @property
    def template_context(self):
        ctxt = super(AdminFacetedReport, self).template_context

        self.run_query(0)
        if self.es_params.get('search'):
            ctxt["search_query"] = self.es_params.get('search')[0]
        ctxt.update({
            'layout_flush_content': True,
            'facet_map': self.es_facet_map,
            'query_str': self.request.META['QUERY_STRING'],
            'facet_prefix': self.es_prefix,
            'facet_report': self,
            'grouped_facets': True,
            'startdate': self.request.GET.get('startdate', ''),
            'enddate': self.request.GET.get('enddate', ''),
            'interval': self.request.GET.get('interval', ''),
        })
        return ctxt

    @property
    def total_records(self):
        return int(self.es_results['hits']['total'])

    def is_custom_param(self, param):
        return param.startswith(self.es_prefix)

    @property
    def shared_pagination_GET_params(self):
        ret = super(AdminFacetedReport, self).shared_pagination_GET_params
        for param in self.request.GET.iterlists():
            if self.is_custom_param(param[0]):
                for val in param[1]:
                    ret.append(dict(name=param[0], value=val))
        return ret

    def es_query(self, params=None, size=None):
        if params is None:
            params = {}
        terms = ['search']
        q = {"query": {"match_all":{}}}

        search_query = params.get('search', "")
        if search_query:
            q['query'] = {
                "bool": {
                    "must": {
                        "match" : {
                            "_all" : {
                                "query" : search_query,
                                "operator" : "and", }}}}}

        q["facets"] = {}

        q["sort"] = self.get_sorting_block()
        start_at=self.pagination.start
        size = size if size is not None else self.pagination.count
        return es_query(params, self.es_facet_list, terms, q, self.es_url, start_at, size, facet_size=25)

    @property
    def es_results(self):
        if not self.es_queried:
            self.run_query()
        return self.es_response

    def run_query(self, size=None):
        self.es_params, _ = parse_args_for_es(self.request, prefix=self.es_prefix)
        results = self.es_query(self.es_params, size)
        self.es_facet_map = fill_mapping_with_facets(self.es_facet_mapping, results, self.es_params)
        self.es_response = results
        self.es_queried = True
        return self.es_response

    @property
    def export_table(self):
        self.pagination.count = 1000000 # terrible hack to get the export to return all rows
        self.show_name = True
        return super(AdminFacetedReport, self).export_table

class AdminUserReport(AdminFacetedReport):
    slug = "user_list"
    name = ugettext_noop('User List')
    facet_title = ugettext_noop("User Facets")
    search_for = ugettext_noop("users...")
    default_sort = {'username.exact': 'asc'}
    es_url = USER_INDEX + '/user/_search'

    es_facet_list = [
        "is_active", # this is NOT "has submitted a form in the last 30 days"
        "is_staff",
        "is_superuser",
        "domain",
        "doc_type",
    ]

    es_facet_mapping = [
        ("", True, [
            {"facet": "is_active", "name": "Can Log In?", "expanded": True },
            {"facet": "is_superuser", "name": "SuperUser?", "expanded": True },
            {"facet": "is_staff", "name": "Staff?", "expanded": True },
            {"facet": "domain", "name": "Domain", "expanded": True },
            {"facet": "doc_type", "name": "User Type", "expanded": True },
        ]),
    ]

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn(_("Username"), prop_name="username.exact"),
            DataTablesColumn(_("Project Spaces")),
            DataTablesColumn(_("Date Joined"), prop_name="date_joined"),
            DataTablesColumn(_("Last Login"), prop_name="last_login"),
            DataTablesColumn(_("Type"), prop_name="doc_type"),
            DataTablesColumn(_("SuperUser?"), prop_name="is_superuser"),
        )
        return headers

    @property
    def rows(self):
        users = [res['_source'] for res in self.es_results.get('hits', {}).get('hits', [])]

        def format_date(dstr, default):
            # use [:19] so that only only the 'YYYY-MM-DDTHH:MM:SS' part of the string is parsed
            return datetime.strptime(dstr[:19], '%Y-%m-%dT%H:%M:%S').strftime('%Y/%m/%d %H:%M:%S') if dstr else default

        def get_domains(user):
            if user.get('doc_type') == "WebUser":
                return ", ".join([dm['domain'] for dm in user.get('domain_memberships', [])])
            return user.get('domain_membership', {}).get('domain', _('No Domain Data'))

        for u in users:
            yield [
                u.get('username'),
                get_domains(u),
                format_date(u.get('date_joined'), _('No date')),
                format_date(u.get('last_login'), _('No date')),
                u.get('doc_type'),
                u.get('is_superuser'),
            ]

def create_mapping_from_list(l, name="", expand_outer=False, expand_inner=False, name_change_fn=None):
    name_change_fn = name_change_fn or (lambda x: x)
    facets = [{"facet": item, "name": name_change_fn(item), "expanded": expand_inner } for item in sorted(l)]
    return (name, expand_outer, facets)

class AdminAppReport(AdminFacetedReport):
    slug = "app_list"
    name = ugettext_noop('Application List')
    facet_title = ugettext_noop("App Facets")
    search_for = ugettext_noop("apps...")
    default_sort = {'name.exact': 'asc'}
    es_url = APP_INDEX + '/app/_search'

    excluded_properties = ["_id", "_rev", "_attachments", "admin_password_charset", "short_odk_url", "version",
                           "admin_password", "built_on", ]
    profile_list = ["profile.%s.%s" % (c['type'], c['id']) for c in CC_SETTINGS if c['type'] != 'hq']
    calculated_properties_mapping = ("Calculations", True,
                                     [{"facet": "cp_is_active", "name": "Active", "expanded": True }])

    @property
    def properties(self):
        return filter(lambda p: p and p not in self.excluded_properties, Application.properties().keys())

    @property
    def es_facet_list(self):
        props = self.properties + self.profile_list + ["cp_is_active"]
        return filter(lambda p: p not in self.excluded_properties, props)

    @property
    def es_facet_mapping(self):
        def remove_profile(name):
            return name[len("profile."):]
        profile_mapping = create_mapping_from_list(self.profile_list, "Profile", True, True, remove_profile)
        other_mapping = create_mapping_from_list(self.properties, "Other")
        return [profile_mapping, self.calculated_properties_mapping, other_mapping]

    @property
    def headers(self):
        headers = DataTablesHeader(
            DataTablesColumn(_("Name"), prop_name="name.exact"),
            DataTablesColumn(_("Project Space"), prop_name="domain"),
            DataTablesColumn(_("Build Comment"), prop_name="build_comment"),
        )
        return headers

    @property
    def rows(self):
        apps = [res['_source'] for res in self.es_results.get('hits', {}).get('hits', [])]

        for app in apps:
            yield [
                app.get('name'),
                app.get('domain'),
                app.get('build_comment'),
            ]


class GlobalAdminReports(AdminReport):
    base_template = "hqadmin/indicator_report.html"
    section_name = ugettext_noop("ADMINREPORT")  # not sure why ...

    @property
    def template_context(self):
        context = super(AdminReport, self).template_context
        indicator_data = copy.deepcopy(INDICATOR_DATA)
        from django.core.urlresolvers import reverse
        for key in self.indicators:
            indicator_data[key]["ajax_url"] = reverse(
                indicator_data[key]["ajax_view"]
            )
            if not ("params_es_dict" in indicator_data[key]):
                indicator_data[key]["params_es_dict"] = {}
            indicator_data[key]["params_es_dict"].update(self.params_es_dict)
            indicator_data[key]["params_es"] = json.dumps(
                indicator_data[key]["params_es_dict"]
            )
        context.update({
            'indicator_data': indicator_data,
            'indicators': self.indicators,
            'report_breadcrumbs': '<a href=".">%s</a>' % self.name,
        })
        return context

    @property
    def domains(self):
        return Domain.get_all()

    @property
    def indicators(self):
        raise NotImplementedError

    @property
    def use_real_project_spaces(self):
        return True

    @property
    def params_es_dict(self):
        params = {}
        if self.use_real_project_spaces:
            params.update({
                "is_test": ["false"],
            })
        return params


class RealProjectSpacesReport(GlobalAdminReports):
    slug = 'real_project_spaces'
    name = ugettext_noop('Real Project Spaces')
    indicators = [
        'domain_count',
        'domain_self_started_count',
    ]


class RealProjectSpacesPlansReport(GlobalAdminReports):
    slug = 'real_project_spaces_plans'
    name = ugettext_noop('Real Project Spaces - Plans')
    indicators = []

    @property
    def headers(self):
        return DataTablesHeader(
            DataTablesColumn(_("# Community Projects")),
            DataTablesColumn(_("# Standard Projects")),
            DataTablesColumn(_("# Pro Projects")),
            DataTablesColumn(_("# Advanced Projects")),
            DataTablesColumn(_("# Enterprise Projects")),
        )

    @property
    def rows(self):
        return [
            [
                Subscription.objects.filter(
                    plan_version__plan__edition=SoftwarePlanEdition.COMMUNITY,
                    is_active=True,
                ).count(),
                Subscription.objects.filter(
                    plan_version__plan__edition=SoftwarePlanEdition.STANDARD,
                    is_active=True,
                ).count(),
                Subscription.objects.filter(
                    plan_version__plan__edition=SoftwarePlanEdition.PRO,
                    is_active=True,
                ).count(),
                Subscription.objects.filter(
                    plan_version__plan__edition=SoftwarePlanEdition.ADVANCED,
                    is_active=True,
                ).count(),
                Subscription.objects.filter(
                    plan_version__plan__edition=SoftwarePlanEdition.ENTERPRISE,
                    is_active=True,
                ).count(),
            ]
        ]


class FormSubmissionsReport(GlobalAdminReports):
    slug = 'form_submissions'
    name = _('Form Submissions')
    indicators = [
        'forms',
        'forms_mobile',
        'forms_web',
    ]


class UserReport(GlobalAdminReports):
    slug = 'user_report'
    name = _('User Report')
    indicators = [
        'users',
        'users_mobile',
        'users_web',
    ]


class CommTrackAdminReport(GlobalAdminReports):
    @property
    def params_es_dict(self):
        params = super(GlobalAdminReports, self).params_es_dict
        params.update({
            "commtrack_enabled": ["T"],
        })
