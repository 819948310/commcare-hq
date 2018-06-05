hqDefine('accounting/js/billing_account_form', [
    'jquery',
    'knockout',
    'hqwebapp/js/initial_page_data',
    'accounting/js/credits_tab',
    'hqwebapp/js/stay_on_tab',
    'accounting/js/widgets',
], function (
    $,
    ko,
    initialPageData
) {
    var billingAccountFormModel = function (isActive, isCustomerBillingAccount) {
        'use strict';
        var self = {};

        self.is_active = ko.observable(isActive);
        self.is_customer_billing_account = ko.observable(isCustomerBillingAccount);
        self.showActiveAccounts = ko.computed(function () {
            return !self.is_active();
        });

        return self;
    };

    $(function () {
        var baForm = billingAccountFormModel(initialPageData.get('account_form_is_active'),
            initialPageData.get('is_customer_billing_account'));
        $('#account-form').koApplyBindings(baForm);

        $("#show_emails").click(function() {
            $('#emails-text').show();
            $(this).parent().hide();
        });
    });
});
