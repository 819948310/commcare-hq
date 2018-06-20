from __future__ import absolute_import
from __future__ import unicode_literals
import uuid
from django.test import TestCase
from corehq.apps.casegroups.models import CommCareCaseGroup
from corehq.apps.data_interfaces.tests.util import create_case
from corehq.apps.domain.shortcuts import create_domain
from corehq.apps.hqcase.utils import update_case
from corehq.apps.groups.models import Group
from corehq.apps.locations.models import SQLLocation
from corehq.apps.locations.tests.util import make_loc, setup_location_types
from corehq.apps.sms.models import PhoneNumber
from corehq.apps.users.models import CommCareUser, WebUser
from corehq.form_processor.interfaces.dbaccessors import CaseAccessors
from corehq.form_processor.tests.utils import run_with_all_backends
from corehq.form_processor.utils import is_commcarecase
from corehq.messaging.scheduling.models import TimedSchedule, TimedEvent, SMSContent, Content
from corehq.messaging.scheduling.scheduling_partitioned.models import (
    CaseScheduleInstanceMixin,
    CaseTimedScheduleInstance,
    ScheduleInstance,
)
from corehq.messaging.scheduling.tests.util import delete_timed_schedules
from corehq.util.test_utils import create_test_case, set_parent_case
from datetime import time
from mock import patch


class SchedulingRecipientTest(TestCase):
    domain = 'scheduling-recipient-test'

    @classmethod
    def setUpClass(cls):
        super(SchedulingRecipientTest, cls).setUpClass()

        cls.domain_obj = create_domain(cls.domain)

        cls.location_types = setup_location_types(cls.domain, ['country', 'state', 'city'])
        cls.country_location = make_loc('usa', domain=cls.domain, type='country')
        cls.state_location = make_loc('ma', domain=cls.domain, type='state', parent=cls.country_location)
        cls.city_location = make_loc('boston', domain=cls.domain, type='city', parent=cls.state_location)

        cls.mobile_user = CommCareUser.create(cls.domain, 'mobile', 'abc')
        cls.mobile_user.set_location(cls.city_location)

        cls.mobile_user2 = CommCareUser.create(cls.domain, 'mobile2', 'abc')
        cls.mobile_user2.set_location(cls.state_location)

        cls.web_user = WebUser.create(cls.domain, 'web', 'abc')

        cls.group = Group(domain=cls.domain, users=[cls.mobile_user.get_id])
        cls.group.save()

        cls.case_group = CommCareCaseGroup(domain=cls.domain)
        cls.case_group.save()

    @classmethod
    def tearDownClass(cls):
        cls.domain_obj.delete()
        super(SchedulingRecipientTest, cls).tearDownClass()

    def tearDown(self):
        delete_timed_schedules(self.domain)
        PhoneNumber.objects.filter(domain=self.domain).delete()
        super(SchedulingRecipientTest, self).tearDown()

    def user_ids(self, users):
        return [user.get_id for user in users]

    @run_with_all_backends
    def test_specific_case_recipient(self):
        with create_case(self.domain, 'person') as case:
            instance = ScheduleInstance(
                domain=self.domain,
                recipient_type=ScheduleInstance.RECIPIENT_TYPE_CASE,
                recipient_id=case.case_id,
            )
            self.assertEqual(instance.recipient.case_id, case.case_id)

        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_CASE,
            recipient_id='id-does-not-exist',
        )
        self.assertIsNone(instance.recipient)

    def test_specific_mobile_worker_recipient(self):
        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_MOBILE_WORKER,
            recipient_id=self.mobile_user.get_id,
        )
        self.assertTrue(isinstance(instance.recipient, CommCareUser))
        self.assertEqual(instance.recipient.get_id, self.mobile_user.get_id)

        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_MOBILE_WORKER,
            recipient_id=self.web_user.get_id,
        )
        self.assertIsNone(instance.recipient)

        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_MOBILE_WORKER,
            recipient_id='id-does-not-exist',
        )
        self.assertIsNone(instance.recipient)

    def test_specific_web_user_recipient(self):
        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_WEB_USER,
            recipient_id=self.web_user.get_id,
        )
        self.assertTrue(isinstance(instance.recipient, WebUser))
        self.assertEqual(instance.recipient.get_id, self.web_user.get_id)

        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_WEB_USER,
            recipient_id=self.mobile_user.get_id,
        )
        self.assertIsNone(instance.recipient)

        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_WEB_USER,
            recipient_id='id-does-not-exist',
        )
        self.assertIsNone(instance.recipient)

    def test_specific_case_group_recipient(self):
        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_CASE_GROUP,
            recipient_id=self.case_group.get_id,
        )
        self.assertTrue(isinstance(instance.recipient, CommCareCaseGroup))
        self.assertEqual(instance.recipient.get_id, self.case_group.get_id)

        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_CASE_GROUP,
            recipient_id='id-does-not-exist',
        )
        self.assertIsNone(instance.recipient)

    def test_specific_group_recipient(self):
        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_USER_GROUP,
            recipient_id=self.group.get_id,
        )
        self.assertTrue(isinstance(instance.recipient, Group))
        self.assertEqual(instance.recipient.get_id, self.group.get_id)

        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_USER_GROUP,
            recipient_id='id-does-not-exist',
        )
        self.assertIsNone(instance.recipient)

    def test_specific_location_recipient(self):
        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_LOCATION,
            recipient_id=self.city_location.location_id,
        )
        self.assertTrue(isinstance(instance.recipient, SQLLocation))
        self.assertEqual(instance.recipient.location_id, self.city_location.location_id)

        instance = ScheduleInstance(
            domain=self.domain,
            recipient_type=ScheduleInstance.RECIPIENT_TYPE_LOCATION,
            recipient_id='id-does-not-exist',
        )
        self.assertIsNone(instance.recipient)

    @run_with_all_backends
    def test_case_recipient(self):
        with create_case(self.domain, 'person') as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id, recipient_type='Self')
            self.assertTrue(is_commcarecase(instance.recipient))
            self.assertEqual(instance.recipient.case_id, case.case_id)

    @run_with_all_backends
    def test_owner_recipient(self):
        with create_case(self.domain, 'person', owner_id=self.city_location.location_id) as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id, recipient_type='Owner')
            self.assertTrue(isinstance(instance.recipient, SQLLocation))
            self.assertEqual(instance.recipient.location_id, self.city_location.location_id)

        with create_case(self.domain, 'person', owner_id=self.group.get_id) as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id, recipient_type='Owner')
            self.assertTrue(isinstance(instance.recipient, Group))
            self.assertEqual(instance.recipient.get_id, self.group.get_id)

        with create_case(self.domain, 'person', owner_id=self.mobile_user.get_id) as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id, recipient_type='Owner')
            self.assertTrue(isinstance(instance.recipient, CommCareUser))
            self.assertEqual(instance.recipient.get_id, self.mobile_user.get_id)

        with create_case(self.domain, 'person', owner_id=self.web_user.get_id) as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id, recipient_type='Owner')
            self.assertTrue(isinstance(instance.recipient, WebUser))
            self.assertEqual(instance.recipient.get_id, self.web_user.get_id)

        with create_case(self.domain, 'person') as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id, recipient_type='Owner')
            self.assertIsNone(instance.recipient)

    @run_with_all_backends
    def test_last_submitting_user_recipient(self):
        with create_test_case(self.domain, 'person', 'Joe', user_id=self.mobile_user.get_id) as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id,
                recipient_type=CaseScheduleInstanceMixin.RECIPIENT_TYPE_LAST_SUBMITTING_USER)
            self.assertTrue(isinstance(instance.recipient, CommCareUser))
            self.assertEqual(instance.recipient.get_id, self.mobile_user.get_id)

        with create_test_case(self.domain, 'person', 'Joe', user_id=self.web_user.get_id) as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id,
                recipient_type=CaseScheduleInstanceMixin.RECIPIENT_TYPE_LAST_SUBMITTING_USER)
            self.assertTrue(isinstance(instance.recipient, WebUser))
            self.assertEqual(instance.recipient.get_id, self.web_user.get_id)

        with create_test_case(self.domain, 'person', 'Joe', user_id='system') as case:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=case.case_id,
                recipient_type=CaseScheduleInstanceMixin.RECIPIENT_TYPE_LAST_SUBMITTING_USER)
            self.assertIsNone(instance.recipient)

    @run_with_all_backends
    def test_parent_case_recipient(self):
        with create_case(self.domain, 'person') as child, create_case(self.domain, 'person') as parent:
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=child.case_id,
                recipient_type=CaseScheduleInstanceMixin.RECIPIENT_TYPE_PARENT_CASE)
            self.assertIsNone(instance.recipient)

            set_parent_case(self.domain, child, parent, relationship='child', identifier='parent')
            instance = CaseTimedScheduleInstance(domain=self.domain, case_id=child.case_id,
                recipient_type=CaseScheduleInstanceMixin.RECIPIENT_TYPE_PARENT_CASE)
            self.assertEqual(instance.recipient.case_id, parent.case_id)

    def test_expand_location_recipients_without_descendants(self):
        schedule = TimedSchedule.create_simple_daily_schedule(
            self.domain,
            TimedEvent(time=time(9, 0)),
            SMSContent(message={'en': 'Hello'})
        )
        schedule.include_descendant_locations = False
        schedule.save()

        instance = CaseTimedScheduleInstance(
            domain=self.domain,
            timed_schedule_id=schedule.schedule_id,
            recipient_type='Location',
            recipient_id=self.country_location.location_id
        )
        self.assertEqual(
            list(instance.expand_recipients()),
            []
        )

        instance = CaseTimedScheduleInstance(
            domain=self.domain,
            timed_schedule_id=schedule.schedule_id,
            recipient_type='Location',
            recipient_id=self.state_location.location_id
        )
        self.assertEqual(
            self.user_ids(instance.expand_recipients()),
            [self.mobile_user2.get_id]
        )

    def test_expand_location_recipients_with_descendants(self):
        schedule = TimedSchedule.create_simple_daily_schedule(
            self.domain,
            TimedEvent(time=time(9, 0)),
            SMSContent(message={'en': 'Hello'})
        )
        schedule.include_descendant_locations = True
        schedule.save()

        instance = CaseTimedScheduleInstance(
            domain=self.domain,
            timed_schedule_id=schedule.schedule_id,
            recipient_type='Location',
            recipient_id=self.state_location.location_id
        )
        self.assertItemsEqual(
            self.user_ids(instance.expand_recipients()),
            [self.mobile_user.get_id, self.mobile_user2.get_id]
        )

    def test_expand_location_recipients_with_location_type_filter(self):
        schedule = TimedSchedule.create_simple_daily_schedule(
            self.domain,
            TimedEvent(time=time(9, 0)),
            SMSContent(message={'en': 'Hello'})
        )
        schedule.include_descendant_locations = True
        schedule.location_type_filter = [self.city_location.location_type_id]
        schedule.save()

        instance = CaseTimedScheduleInstance(
            domain=self.domain,
            timed_schedule_id=schedule.schedule_id,
            recipient_type='Location',
            recipient_id=self.country_location.location_id
        )
        self.assertItemsEqual(
            self.user_ids(instance.expand_recipients()),
            [self.mobile_user.get_id]
        )

    def test_expand_group_recipients(self):
        instance = CaseTimedScheduleInstance(domain=self.domain, recipient_type='Group',
            recipient_id=self.group.get_id)
        self.assertEqual(
            self.user_ids(instance.expand_recipients()),
            [self.mobile_user.get_id]
        )

    def create_user_case(self, user):
        create_case_kwargs = {
            'external_id': user.get_id,
            'update': {'hq_user_id': user.get_id},
        }
        return create_case(self.domain, 'commcare-user', **create_case_kwargs)

    def assertPhoneEntryCount(self, count, only_count_two_way=False):
        qs = PhoneNumber.objects.filter(domain=self.domain)
        if only_count_two_way:
            qs = qs.filter(is_two_way=True)
        self.assertEqual(qs.count(), count)

    def assertTwoWayEntry(self, entry, expected_phone_number):
        self.assertTrue(isinstance(entry, PhoneNumber))
        self.assertEqual(entry.phone_number, expected_phone_number)
        self.assertTrue(entry.is_two_way)

    @run_with_all_backends
    def test_one_way_numbers(self):
        user1 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
        user2 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
        user3 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
        self.addCleanup(user1.delete)
        self.addCleanup(user2.delete)
        self.addCleanup(user3.delete)

        self.assertIsNone(user1.memoized_usercase)
        self.assertIsNone(Content.get_two_way_entry_or_phone_number(user1))

        with self.create_user_case(user2) as case:
            self.assertIsNotNone(user2.memoized_usercase)
            self.assertIsNone(Content.get_two_way_entry_or_phone_number(user2))
            self.assertIsNone(Content.get_two_way_entry_or_phone_number(case))

        with self.create_user_case(user3) as case:
            # If the user has no number, the user case's number is used
            update_case(self.domain, case.case_id, case_properties={'contact_phone_number': '12345678'})
            case = CaseAccessors(self.domain).get_case(case.case_id)
            self.assertPhoneEntryCount(1)
            self.assertPhoneEntryCount(0, only_count_two_way=True)
            self.assertIsNotNone(user3.memoized_usercase)
            self.assertEqual(Content.get_two_way_entry_or_phone_number(user3), '12345678')

            # If the user has a number, it is used before the user case's number
            user3.add_phone_number('87654321')
            user3.save()
            self.assertPhoneEntryCount(2)
            self.assertPhoneEntryCount(0, only_count_two_way=True)
            self.assertEqual(Content.get_two_way_entry_or_phone_number(user3), '87654321')

            # Referencing the case directly uses the case's phone number
            self.assertEqual(Content.get_two_way_entry_or_phone_number(case), '12345678')

    @run_with_all_backends
    def test_ignoring_entries(self):
        with create_case(self.domain, 'person') as case:
            update_case(self.domain, case.case_id,
                case_properties={'contact_phone_number': '12345', 'contact_phone_number_is_verified': '1'})

            self.assertPhoneEntryCount(1)
            self.assertPhoneEntryCount(1, only_count_two_way=True)

            with patch('corehq.apps.sms.tasks.use_phone_entries') as patch1, \
                    patch('corehq.messaging.tasks.use_phone_entries') as patch2, \
                    patch('corehq.messaging.scheduling.models.abstract.use_phone_entries') as patch3:

                patch1.return_value = patch2.return_value = patch3.return_value = False
                update_case(self.domain, case.case_id, case_properties={'contact_phone_number': '23456'})
                case = CaseAccessors(self.domain).get_case(case.case_id)

                self.assertPhoneEntryCount(1)
                self.assertPhoneEntryCount(1, only_count_two_way=True)
                self.assertTwoWayEntry(PhoneNumber.objects.get(owner_id=case.case_id), '12345')
                self.assertEqual(Content.get_two_way_entry_or_phone_number(case), '23456')

    @run_with_all_backends
    def test_two_way_numbers(self):
        user1 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
        user2 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
        user3 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
        self.addCleanup(user1.delete)
        self.addCleanup(user2.delete)
        self.addCleanup(user3.delete)

        self.assertIsNone(user1.memoized_usercase)
        self.assertIsNone(Content.get_two_way_entry_or_phone_number(user1))

        with self.create_user_case(user2) as case:
            self.assertIsNotNone(user2.memoized_usercase)
            self.assertIsNone(Content.get_two_way_entry_or_phone_number(user2))
            self.assertIsNone(Content.get_two_way_entry_or_phone_number(case))

        with self.create_user_case(user3) as case:
            # If the user has no number, the user case's number is used
            update_case(self.domain, case.case_id,
                case_properties={'contact_phone_number': '12345678', 'contact_phone_number_is_verified': '1'})
            case = CaseAccessors(self.domain).get_case(case.case_id)
            self.assertPhoneEntryCount(1)
            self.assertPhoneEntryCount(1, only_count_two_way=True)
            self.assertIsNotNone(user3.memoized_usercase)
            self.assertTwoWayEntry(Content.get_two_way_entry_or_phone_number(user3), '12345678')

            # If the user has a number, it is used before the user case's number
            user3.add_phone_number('87654321')
            user3.save()
            PhoneNumber.objects.get(phone_number='87654321').set_two_way()
            self.assertPhoneEntryCount(2)
            self.assertPhoneEntryCount(2, only_count_two_way=True)
            self.assertTwoWayEntry(Content.get_two_way_entry_or_phone_number(user3), '87654321')

            # Referencing the case directly uses the case's phone number
            self.assertTwoWayEntry(Content.get_two_way_entry_or_phone_number(case), '12345678')

    @run_with_all_backends
    def test_not_using_phone_entries(self):
        with patch('corehq.apps.sms.tasks.use_phone_entries') as patch1, \
                patch('corehq.messaging.tasks.use_phone_entries') as patch2, \
                patch('corehq.messaging.scheduling.models.abstract.use_phone_entries') as patch3:

            patch1.return_value = patch2.return_value = patch3.return_value = False

            user1 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
            user2 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
            user3 = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
            self.addCleanup(user1.delete)
            self.addCleanup(user2.delete)
            self.addCleanup(user3.delete)

            self.assertIsNone(user1.memoized_usercase)
            self.assertIsNone(Content.get_two_way_entry_or_phone_number(user1))

            with self.create_user_case(user2) as case:
                self.assertIsNotNone(user2.memoized_usercase)
                self.assertIsNone(Content.get_two_way_entry_or_phone_number(user2))
                self.assertIsNone(Content.get_two_way_entry_or_phone_number(case))

            with self.create_user_case(user3) as case:
                # If the user has no number, the user case's number is used
                update_case(self.domain, case.case_id, case_properties={'contact_phone_number': '12345678'})
                case = CaseAccessors(self.domain).get_case(case.case_id)
                self.assertPhoneEntryCount(0)
                self.assertIsNotNone(user3.memoized_usercase)
                self.assertEqual(Content.get_two_way_entry_or_phone_number(user3), '12345678')

                # If the user has a number, it is used before the user case's number
                user3.add_phone_number('87654321')
                user3.save()
                self.assertPhoneEntryCount(0)
                self.assertEqual(Content.get_two_way_entry_or_phone_number(user3), '87654321')

                # Referencing the case directly uses the case's phone number
                self.assertEqual(Content.get_two_way_entry_or_phone_number(case), '12345678')

    @run_with_all_backends
    def test_phone_number_preference(self):
        user = CommCareUser.create(self.domain, uuid.uuid4().hex, 'abc')
        self.addCleanup(user.delete)

        user.add_phone_number('12345')
        user.add_phone_number('23456')
        user.add_phone_number('34567')
        user.save()

        self.assertPhoneEntryCount(3)
        self.assertPhoneEntryCount(0, only_count_two_way=True)
        self.assertEqual(Content.get_two_way_entry_or_phone_number(user), '12345')

        PhoneNumber.objects.get(phone_number='23456').set_two_way()
        self.assertPhoneEntryCount(3)
        self.assertPhoneEntryCount(1, only_count_two_way=True)
        self.assertTwoWayEntry(Content.get_two_way_entry_or_phone_number(user), '23456')
