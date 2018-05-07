# coding=utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from custom.yeksi_naa_reports.filters import LocationFilter, MonthsDateFilter, ProgramFilter
from custom.yeksi_naa_reports.sqldata import AvailabilityData, RuptureRateByPPSData
from custom.yeksi_naa_reports.utils import MultiReport
from django.utils.functional import cached_property


class Dashboard1Report(MultiReport):
    title = "Tableau de Bord 1"
    fields = [MonthsDateFilter, ProgramFilter, LocationFilter]
    name = "Tableau de Bord 1"
    slug = 'tableau_de_bord_1'
    default_rows = 10
    exportable = True

    @cached_property
    def data_providers(self):
        return [
            AvailabilityData(config=self.report_config),
            RuptureRateByPPSData(config=self.report_config),
        ]
