# coding=utf-8
from __future__ import absolute_import
from __future__ import unicode_literals
from custom.intrahealth.reports.dashboard_1 import Dashboard1Report
from custom.intrahealth.reports.dashboard_2 import Dashboard2Report
from custom.intrahealth.reports.dashboard_3 import Dashboard3Report
from custom.intrahealth.reports.tableu_de_board_report_v2 import TableuDeBoardReport2
from custom.intrahealth.reports.fiche_consommation_report_v2 import FicheConsommationReport2
from custom.intrahealth.reports.recap_passage_report_v2 import RecapPassageReport2

CUSTOM_REPORTS = (
    ("Rapports Yeksi Naa", (
        Dashboard1Report,
        Dashboard2Report,
        Dashboard3Report,
    )),
    ("INFORMED PUSH MODEL REPORTS UCR", (
        TableuDeBoardReport2,
        FicheConsommationReport2,
        RecapPassageReport2,
    ))
)
