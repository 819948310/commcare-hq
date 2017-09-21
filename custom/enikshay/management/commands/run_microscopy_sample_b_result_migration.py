from custom.enikshay.management.commands.utils import BaseEnikshayCaseMigration, get_result_recorded_form


class Command(BaseEnikshayCaseMigration):
    case_type = 'test'
    case_properties_to_update = [
        'microscopy_sample_b_result',
    ]
    datamigration_case_property = 'datamigration_microscopy_sample_b_result'

    @staticmethod
    def get_case_property_updates(test, domain):
        if (
            test.get_case_property('datamigration_microscopy_sample_b_result') == 'yes'
            or test.get_case_property('migration_created_case') == 'true'
            or test.get_case_property('test_type') not in ['microscopy-zn', 'microscopy-fluorescent']
            or test.get_case_property('result_recorded') != 'yes'
            or test.get_case_property('microscopy_sample_b_result')
        ):
            return {}
        else:
            form_data = get_result_recorded_form(test)
            if form_data is None:
                return {}
            microscopy_sample_b_result = (
                form_data.get('microscopy', {}).get(
                    'ql_sample_b', {}).get('sample_b_result')
                or form_data.get('update_test_result', {}).get('microscopy', {}).get(
                    'ql_result', {}).get('sample_b_result')
            )
            if microscopy_sample_b_result:
                return {
                    'microscopy_sample_b_result': microscopy_sample_b_result,
                }
            else:
                return {}
