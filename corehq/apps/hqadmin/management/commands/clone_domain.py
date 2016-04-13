from optparse import make_option

from django.core.management.base import BaseCommand

from corehq.apps.userreports.dbaccessors import get_report_configs_for_domain, get_datasources_for_domain


class Command(BaseCommand):
    args = "<existing_domain> <new_domain>"
    help = """Clone a domain and it's data"""

    option_list = BaseCommand.option_list + (
        make_option('--no-flags', action='store_false', dest='flags', default=True,
                    help="Don't process domain flags"),
        make_option('--no-fixtures', action='store_false', dest='fixtures', default=True,
                    help="Don't process fixtures"),
        make_option('--no-locations', action='store_false', dest='locations', default=True,
                    help="Don't process locations"),
        make_option('--no-products', action='store_false', dest='products', default=True,
                    help="Don't process products"),
        make_option('--no-ucr-or-apps', action='store_false', dest='ucr_apps', default=True,
                    help="Don't process UCR"),
    )

    def handle(self, flags=True, fixtures=True, locations=True, products=True, ucr_apps=True, *args, **options):
        existing_domain, new_domain = args
        self.clone_domain_and_settings(existing_domain, new_domain)
        if flags:
            self.set_flags(existing_domain, new_domain)

        if fixtures:
            self.copy_fixtures(existing_domain, new_domain)

        if locations:
            self.copy_locations(existing_domain, new_domain)

        if products:
            self.copy_products(existing_domain, new_domain)

        if ucr_apps:
            report_map = self.copy_ucr_data(existing_domain, new_domain)
            self.copy_applications(existing_domain, new_domain, report_map)

    def clone_domain_and_settings(self, old_domain, new_domain):
        from corehq.apps.domain.models import Domain
        domain = Domain.get_by_name(old_domain)
        domain.name = new_domain
        self.save_couch_copy(domain)

        from corehq.apps.commtrack.models import CommtrackConfig
        commtrack_config = CommtrackConfig.for_domain(domain)
        self.save_couch_copy(commtrack_config, new_domain)

    def set_flags(self, old_domain, new_domain):
        from corehq.toggles import all_toggles, NAMESPACE_DOMAIN
        from corehq.feature_previews import all_previews
        from corehq.apps.hqwebapp.templatetags.hq_shared_tags import toggle_js_domain_cachebuster

        for toggle in all_toggles():
            if toggle.enabled(old_domain):
                toggle.set(new_domain, True, NAMESPACE_DOMAIN)

        for preview in all_previews():
            if preview.enabled(old_domain):
                preview.set(new_domain, True, NAMESPACE_DOMAIN)
                if preview.save_fn is not None:
                    preview.save_fn(new_domain, True)

        toggle_js_domain_cachebuster.clear(new_domain)

    def copy_fixtures(self, old_domain, new_domain):
        from corehq.apps.fixtures.models import FixtureDataItem
        from corehq.apps.fixtures.dbaccessors import get_fixture_data_types_in_domain

        fixture_types = get_fixture_data_types_in_domain(old_domain)
        for fixture_type in fixture_types:
            old_id, new_id = self.save_couch_copy(fixture_type, new_domain)
            for item in FixtureDataItem.by_data_type(old_domain, old_id):
                item.data_type_id = new_id
                self.save_couch_copy(item, new_domain)

        # TODO: FixtureOwnership - requires copying users & groups

    def copy_locations(self, old_domain, new_domain):
        from corehq.apps.locations.models import LocationType
        from corehq.apps.locations.models import Location

        location_types = LocationType.objects.filter(domain=old_domain)
        for location_type in location_types:
            self.save_sql_copy(location_type, new_domain)

        def copy_location_hierarchy(location, id_map):
            new_lineage = []
            for ancestor in location.lineage:
                try:
                    new_lineage.appen(id_map[ancestor])
                except KeyError:
                    self.stderr.write("Ancestor {} for location {} missing".format(location._id, ancestor))
            location.lineage = new_lineage

            old_id, new_id = self.save_couch_copy(location, new_domain)
            id_map[old_id] = new_id
            for child in location.children:
                copy_location_hierarchy(child, id_map)

        locations = Location.root_locations(old_domain)
        for location in locations:
            copy_location_hierarchy(location, {})
            
    def copy_products(self, old_domain, new_domain):
        from corehq.apps.products.models import Product
        from corehq.apps.programs.models import Program
        
        program_map = {}
        programs = Program.by_domain(old_domain)
        for program in programs:
            old_id, new_id = self.save_couch_copy(program)
            program_map[old_id] = new_id
            
        products = Product.by_domain(old_domain)
        for product in products:
            if product.program_id:
                try:
                    product.program_id = program_map[product.program_id]
                except:
                    self.stderr('Missing program {} for product {}'.format(product.program_id, product._id))
            self.save_couch_copy(product)

    def copy_applications(self, old_domain, new_domain, report_map):
        from corehq.apps.app_manager.dbaccessors import get_apps_in_domain
        from corehq.apps.app_manager.models import ReportModule
        apps = get_apps_in_domain(old_domain)
        for app in apps:
            for module in app.modules:
                if module.module_type == ReportModule.module_type:
                    for config in module.report_configs:
                        config.report_id = report_map[config.report_id]

            self.save_couch_copy(app, new_domain)

    def copy_ucr_data(self, old_domain, new_domain):
        datasource_map = self.copy_ucr_datasources(new_domain, old_domain)
        report_map = self.copy_ucr_reports(datasource_map, new_domain)
        return report_map

    def copy_ucr_reports(self, datasource_map, new_domain):
        report_map = {}
        reports = get_report_configs_for_domain('icds-sql')
        for report in reports:
            old_datasource_id = report.config_id
            try:
                report.config_id = datasource_map[old_datasource_id]
            except KeyError:
                pass  # datasource not found

            old_id, new_id = self.save_couch_copy(report, new_domain)
            report_map[old_id] = new_id
        return report_map

    def copy_ucr_datasources(self, new_domain, old_domain):
        datasource_map = {}
        datasources = get_datasources_for_domain(old_domain)
        for datasource in datasources:
            datasource.meta.build.finished = False
            datasource.meta.build.initiated = None

            old_id, new_id = self.save_couch_copy(datasource, new_domain)
            datasource_map[old_id] = new_id
        return datasource_map

    def save_couch_copy(self, doc, new_domain=None):
        old_id = doc._id
        del doc._id
        del doc['_rev']
        if new_domain:
            doc.domain = new_domain
        doc.save()
        new_id = doc._id
        self.log_copy(doc.doc_type, old_id, new_id)
        return old_id, new_id

    def save_sql_copy(self, model, new_domain):
        old_id = model.id
        model.domain = new_domain
        model.id = None
        model.save()
        new_id = model.id
        self.log_copy(model.__class__.__name__, old_id, new_id)
        return old_id, new_id

    def log_copy(self, name, old_id, new_id):
        self.stdout.write("{name}(id={old_id}) -> {name}(id={new_id})".format(
            name=name, old_id=old_id, new_id=new_id
        ))
