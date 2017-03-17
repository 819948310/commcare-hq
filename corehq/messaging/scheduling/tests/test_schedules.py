from corehq.apps.domain.models import Domain
from corehq.apps.users.models import CommCareUser
from corehq.form_processor.tests.utils import partitioned
from corehq.messaging.scheduling.scheduling_partitioned.dbaccessors import (
    save_timed_schedule_instance,
    delete_timed_schedule_instance,
    get_timed_schedule_instances_for_schedule,
)
from corehq.messaging.scheduling.models import (
    TimedSchedule,
    SMSContent,
)
from corehq.messaging.scheduling.tasks import (
    refresh_timed_schedule_instances,
)
from corehq.messaging.scheduling.scheduling_partitioned.models import (
    TimedScheduleInstance,
)
from datetime import datetime, date, time
from django.test import TestCase
from mock import patch


@partitioned
@patch('corehq.messaging.scheduling.models.content.SMSContent.send')
@patch('corehq.messaging.scheduling.util.utcnow')
class DailyScheduleTest(TestCase):

    @classmethod
    def setUpClass(cls):
        super(DailyScheduleTest, cls).setUpClass()
        cls.domain = 'scheduling-test'
        cls.domain_obj = Domain(name=cls.domain, default_timezone='America/New_York')
        cls.domain_obj.save()
        cls.user1 = CommCareUser.create(cls.domain, 'user1', 'password')
        cls.user2 = CommCareUser.create(cls.domain, 'user2', 'password')
        cls.schedule = TimedSchedule.create_simple_daily_schedule(
            cls.domain,
            time(12, 0),
            SMSContent(),
            total_iterations=2,
        )

    @classmethod
    def tearDownClass(cls):
        cls.schedule.delete()
        cls.domain_obj.delete()
        super(DailyScheduleTest, cls).tearDownClass()

    def tearDown(self):
        for instance in get_timed_schedule_instances_for_schedule(self.schedule):
            delete_timed_schedule_instance(instance)

    def assertTimedScheduleInstance(self, instance, current_event_num, schedule_iteration_num,
            next_event_due, active, start_date, recipient):
        self.assertEqual(instance.domain, self.domain)
        self.assertEqual(instance.recipient_type, recipient.doc_type)
        self.assertEqual(instance.recipient_id, recipient.get_id)
        self.assertEqual(instance.timed_schedule_id, self.schedule.schedule_id)
        self.assertEqual(instance.current_event_num, current_event_num)
        self.assertEqual(instance.schedule_iteration_num, schedule_iteration_num)
        self.assertEqual(instance.next_event_due, next_event_due)
        self.assertEqual(instance.active, active)
        self.assertEqual(instance.start_date, start_date)

    def assertNumInstancesForSchedule(self, num):
        self.assertEqual(len(list(get_timed_schedule_instances_for_schedule(self.schedule))), num)

    def test_schedule_start_to_finish(self, utcnow_patch, send_patch):
        self.assertNumInstancesForSchedule(0)

        # Schedule the instance
        utcnow_patch.return_value = datetime(2017, 3, 16, 6, 0)
        refresh_timed_schedule_instances(self.schedule, (('CommCareUser', self.user1.get_id),), date(2017, 3, 16))
        self.assertNumInstancesForSchedule(1)
        [instance] = get_timed_schedule_instances_for_schedule(self.schedule)
        self.assertTimedScheduleInstance(instance, 0, 1, datetime(2017, 3, 16, 16, 0), True, date(2017, 3, 16),
            self.user1)
        self.assertEqual(send_patch.call_count, 0)

        # Send first event
        utcnow_patch.return_value = datetime(2017, 3, 16, 16, 1)
        instance.handle_current_event()
        save_timed_schedule_instance(instance)
        self.assertNumInstancesForSchedule(1)
        self.assertTimedScheduleInstance(instance, 0, 2, datetime(2017, 3, 17, 16, 0), True, date(2017, 3, 16),
            self.user1)
        self.assertEqual(send_patch.call_count, 1)

        # Send second (and final) event
        utcnow_patch.return_value = datetime(2017, 3, 17, 16, 1)
        instance.handle_current_event()
        save_timed_schedule_instance(instance)
        self.assertNumInstancesForSchedule(1)
        self.assertTimedScheduleInstance(instance, 0, 3, datetime(2017, 3, 18, 16, 0), False, date(2017, 3, 16),
            self.user1)
        self.assertEqual(send_patch.call_count, 2)

    def test_recalculate_schedule(self, utcnow_patch, send_patch):
        self.assertNumInstancesForSchedule(0)

        # Schedule the instance
        utcnow_patch.return_value = datetime(2017, 3, 16, 6, 0)
        refresh_timed_schedule_instances(self.schedule, (('CommCareUser', self.user1.get_id),), date(2017, 3, 16))
        self.assertNumInstancesForSchedule(1)
        [instance] = get_timed_schedule_instances_for_schedule(self.schedule)
        self.assertTimedScheduleInstance(instance, 0, 1, datetime(2017, 3, 16, 16, 0), True, date(2017, 3, 16),
            self.user1)
        self.assertEqual(send_patch.call_count, 0)

        # Set start date one day back
        refresh_timed_schedule_instances(self.schedule, (('CommCareUser', self.user1.get_id),), date(2017, 3, 15))
        old_id = instance.schedule_instance_id
        self.assertNumInstancesForSchedule(1)
        [instance] = get_timed_schedule_instances_for_schedule(self.schedule)
        self.assertEqual(instance.schedule_instance_id, old_id)
        self.assertTimedScheduleInstance(instance, 0, 2, datetime(2017, 3, 16, 16, 0), True, date(2017, 3, 15),
            self.user1)
        self.assertEqual(send_patch.call_count, 0)

        # Set start date one more day back
        refresh_timed_schedule_instances(self.schedule, (('CommCareUser', self.user1.get_id),), date(2017, 3, 14))
        old_id = instance.schedule_instance_id
        self.assertNumInstancesForSchedule(1)
        [instance] = get_timed_schedule_instances_for_schedule(self.schedule)
        self.assertEqual(instance.schedule_instance_id, old_id)
        self.assertTimedScheduleInstance(instance, 0, 3, datetime(2017, 3, 16, 16, 0), False, date(2017, 3, 14),
            self.user1)
        self.assertEqual(send_patch.call_count, 0)

    def test_keep_in_sync_with_recipients(self, utcnow_patch, send_patch):
        self.assertNumInstancesForSchedule(0)

        # Schedule the instance for user1
        utcnow_patch.return_value = datetime(2017, 3, 16, 6, 0)
        refresh_timed_schedule_instances(self.schedule, (('CommCareUser', self.user1.get_id),), date(2017, 3, 16))
        self.assertNumInstancesForSchedule(1)
        [instance] = get_timed_schedule_instances_for_schedule(self.schedule)
        self.assertTimedScheduleInstance(instance, 0, 1, datetime(2017, 3, 16, 16, 0), True, date(2017, 3, 16),
            self.user1)

        # Add user2
        refresh_timed_schedule_instances(self.schedule,
            (('CommCareUser', self.user1.get_id), ('CommCareUser', self.user2.get_id)), date(2017, 3, 16))

        self.assertNumInstancesForSchedule(2)
        [instance1, instance2] = get_timed_schedule_instances_for_schedule(self.schedule)
        if instance1.recipient_id == self.user1.get_id:
            user1_instance = instance1
            user2_instance = instance2
        else:
            user1_instance = instance2
            user2_instance = instance1

        self.assertTimedScheduleInstance(user1_instance, 0, 1, datetime(2017, 3, 16, 16, 0), True,
            date(2017, 3, 16), self.user1)
        self.assertTimedScheduleInstance(user2_instance, 0, 1, datetime(2017, 3, 16, 16, 0), True,
            date(2017, 3, 16), self.user2)

        # Remove user1
        refresh_timed_schedule_instances(self.schedule, (('CommCareUser', self.user2.get_id),), date(2017, 3, 16))
        self.assertNumInstancesForSchedule(1)
        [instance] = get_timed_schedule_instances_for_schedule(self.schedule)
        self.assertTimedScheduleInstance(instance, 0, 1, datetime(2017, 3, 16, 16, 0), True, date(2017, 3, 16),
            self.user2)

        self.assertEqual(send_patch.call_count, 0)
