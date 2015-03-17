import json
from datetime import datetime
from django.core.management import BaseCommand, CommandError
from dimagi.utils.web import json_handler
from commcarehq.apps.importer.tasks import do_import
from commcarehq.apps.importer.util import ImporterConfig, ExcelFile
from commcarehq.apps.users.models import WebUser


class Command(BaseCommand):
    help = "import cases from excel manually."
    args = '<import_file> <config_file> <domain> <user>'
    label = "import cases from excel manually."

    def handle(self, *args, **options):
        if len(args) != 4:
            raise CommandError('Usage is import_cases %s' % self.args)

        start = datetime.now()
        export_file, config_file, domain, user_id = args
        if '@' in user_id:
            user = WebUser.get_by_username(user_id)
        else:
            user = WebUser.get(user_id)
        if not user.is_member_of(domain):
            raise CommandError("%s can't access %s" % (user, domain))

        with open(config_file, 'r') as f:
            config = ImporterConfig.from_json(f.read())

        config.couch_user_id = user._id
        spreadsheet = ExcelFile(export_file, True)
        print json.dumps(do_import(spreadsheet, config, domain),
                         default=json_handler)
        print 'finished in %s seconds' % (datetime.now() - start).seconds
