/* globals hqDefine, ko, $, _, gettext */

hqDefine('openmrs/js/openmrs_importers', function () {
    'use strict';

    var module = {};

    var OpenmrsImporter = function (properties) {
        var self = this;

        self.server_url = ko.observable(properties["server_url"]);
        // We are using snake_case for property names so that they
        // match Django form field names. That way we can iterate the
        // fields of an unbound Django form in
        // openmrs_importer_template.html and bind to these properties
        // using the Django form field names.
        self.username = ko.observable(properties["username"]);
        self.password = ko.observable(properties["password"]);
        self.location_id = ko.observable(properties["location_id"]);
        self.import_frequency = ko.observable(properties["import_frequency"]);
        self.log_level = ko.observable(properties["log_level"]);
        self.report_uuid = ko.observable(properties["report_uuid"]);
        self.report_params = ko.observable(properties["report_params"]);
        self.case_type = ko.observable(properties["case_type"]);
        self.owner_id = ko.observable(properties["owner_id"]);
        self.location_type_name = ko.observable(properties["location_type_name"]);
        self.external_id_column = ko.observable(properties["external_id_column"]);
        self.name_columns = ko.observable(properties["name_columns"]);
        self.column_map = ko.observable(properties["column_map"]);

        self.import_frequency_options = [
            {"value": "weekly", "text": gettext("Weekly")},
            {"value": "monthly", "text": gettext("Monthly")},
        ];
        self.log_level_options = [
            {"value": 99, "text": gettext("Disable logging")},
            {"value": 40, "text": "Error"},  // Don't translate the names of log levels
            {"value": 20, "text": "Info"},
        ];

        self.serialize = function () {
            return {
                "server_url": self.server_url(),
                "username": self.username(),
                "password": self.password(),
                "location_id": self.location_id(),
                "import_frequency": self.import_frequency(),
                "log_level": self.log_level(),
                "report_uuid": self.report_uuid(),
                "report_params": self.report_params(),
                "case_type": self.case_type(),
                "owner_id": self.owner_id(),
                "location_type_name": self.location_type_name(),
                "external_id_column": self.external_id_column(),
                "name_columns": self.name_columns(),
                "column_map": self.column_map(),
            };
        };
    };

    module.OpenmrsImporters = function (openmrsImporters, importNowUrl) {
        var self = this;
        var alert_user = hqImport("hqwebapp/js/alert_user").alert_user;

        self.openmrsImporters = ko.observableArray();

        self.init = function () {
            if (openmrsImporters.length > 0) {
                for (var i = 0; i < openmrsImporters.length; i++) {
                    var openmrsImporter = new OpenmrsImporter(openmrsImporters[i]);
                    self.openmrsImporters.push(openmrsImporter);
                }
            } else {
                self.addOpenmrsImporter();
            }
        };

        self.addOpenmrsImporter = function () {
            self.openmrsImporters.push(new OpenmrsImporter({}));
        };

        self.removeOpenmrsImporter = function (openmrsImporter) {
            self.openmrsImporters.remove(openmrsImporter);
        };

        self.submit = function (form) {
            var openmrsImporters = [];
            for (var i = 0; i < self.openmrsImporters().length; i++) {
                var openmrsImporter = self.openmrsImporters()[i];
                openmrsImporters.push(openmrsImporter.serialize());
            }
            $.post(
                form.action,
                {'openmrs_importers': JSON.stringify(openmrsImporters)},
                function (data) { alert_user(data['message'], 'success', true); }
            ).fail(function () { alert_user(gettext('Unable to save OpenMRS Importers'), 'danger'); });
        };

        self.importNow = function () {
            $.post(importNowUrl, {}, function () {
                alert_user(gettext("Importing from OpenMRS will begin shortly."), "success");
            }).fail(function () {
                alert_user(gettext("Failed to schedule task to import from OpenMRS."), "danger");
            });
        };
    };
    return module;
});