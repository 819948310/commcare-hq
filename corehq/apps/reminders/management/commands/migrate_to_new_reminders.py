from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from corehq.apps.data_interfaces.models import (
    AutomaticUpdateRule,
    MatchPropertyDefinition,
    CreateScheduleInstanceActionDefinition,
)
from corehq.apps.domain.models import Domain
from corehq.apps.reminders.models import (
    CaseReminder,
    CaseReminderHandler,
    REMINDER_TYPE_DEFAULT,
    REMINDER_TYPE_ONE_TIME,
    REMINDER_TYPE_KEYWORD_INITIATED,
    REMINDER_TYPE_SURVEY_MANAGEMENT,
    UI_SIMPLE_FIXED,
    EVENT_AS_OFFSET,
    METHOD_SMS,
    METHOD_SMS_CALLBACK,
    METHOD_SMS_SURVEY,
    METHOD_IVR_SURVEY,
    METHOD_EMAIL,
    RECIPIENT_USER,
    RECIPIENT_OWNER,
    RECIPIENT_CASE,
    RECIPIENT_SURVEY_SAMPLE,
    RECIPIENT_PARENT_CASE,
    RECIPIENT_SUBCASE,
    RECIPIENT_USER_GROUP,
    RECIPIENT_LOCATION,
    CASE_CRITERIA,
    MATCH_EXACT,
    MATCH_REGEX,
    MATCH_ANY_VALUE,
    DAY_ANY,
)
from corehq.messaging.scheduling.models import (
    AlertSchedule,
    AlertEvent,
    TimedSchedule,
    SMSContent,
    EmailContent,
)
from corehq.messaging.scheduling.scheduling_partitioned.models import (
    CaseScheduleInstanceMixin,
    CaseAlertScheduleInstance,
)
from corehq.toggles import REMINDERS_MIGRATION_IN_PROGRESS
from datetime import time
from django.db import transaction
from django.core.management.base import BaseCommand
from six import moves


class BaseMigrator(object):

    def migrate(self):
        raise NotImplementedError

    def migrate_schedule_instances(self):
        raise NotImplementedError


class CaseReminderHandlerMigrator(BaseMigrator):

    def __init__(self, handler, rule_migration_function, schedule_migration_function):
        self.handler = handler
        self.rule_migration_function = rule_migration_function
        self.schedule_migration_function = schedule_migration_function

    def migrate(self):
        with transaction.atomic():
            self.schedule = self.schedule_migration_function(self.handler)
            self.rule = self.rule_migration_function(self.handler, self.schedule)

    def migrate_schedule_instances(self):
        if not isinstance(self.schedule, AlertSchedule):
            raise TypeError("Expected AlertSchedule")

        seen_case_ids = set()
        recipient = self.rule.memoized_actions[0].definition.recipients[0]

        for reminder in CaseReminder.view(
            'reminders/by_domain_handler_case',
            startkey=[self.handler.domain, self.handler._id],
            endkey=[self.handler.domain, self.handler._id, {}],
            include_docs=True
        ).all():
            if reminder.case_id in seen_case_ids:
                continue

            seen_case_ids.add(reminder.case_id)

            instance = CaseAlertScheduleInstance(
                domain=self.rule.domain,
                recipient_type=recipient[0],
                recipient_id=recipient[1],
                current_event_num=reminder.current_event_sequence_num,
                schedule_iteration_num=reminder.schedule_iteration_num,
                next_event_due=reminder.next_fire,
                active=reminder.active,
                alert_schedule_id=self.schedule.schedule_id,
                case_id=reminder.case_id,
                rule_id=self.rule.pk,
            )

            if reminder.active and reminder.error:
                self.schedule.move_to_next_event_not_in_the_past(instance)

            instance.save(force_insert=True)


class BroadcastMigrator(BaseMigrator):

    def __init__(self, handler, broadcast_migration_function, schedule_migration_function):
        self.handler = handler
        self.broadcast_migration_function = broadcast_migration_function
        self.schedule_migration_function = schedule_migration_function


def get_extra_scheduling_options(handler):
    if handler.reminder_type == REMINDER_TYPE_DEFAULT and handler.include_child_locations:
        raise ValueError("Unexpected value for include_child_locations for %s" % handler._id)

    return {
        'active': handler.active,
        'default_language_code': handler.default_lang,
        'include_descendant_locations': handler.include_child_locations,
    }


def check_days_until(message_dict):
    for lang, message in message_dict.items():
        if '.days_until' in message:
            raise ValueError(".days_until is not supported")


def get_content(handler, event):
    if handler.method == METHOD_SMS:
        check_days_until(event.message)
        return SMSContent(message=event.message)
    elif handler.method == METHOD_EMAIL:
        check_days_until(event.subject)
        check_days_until(event.message)
        return EmailContent(subject=event.subject, message=event.message)
    else:
        raise ValueError("Unexpected method '%s'" % handler.method)


def get_event(handler, event):
    if handler.event_interpretation == EVENT_AS_OFFSET:
        return AlertEvent(
            minutes_to_wait=(
                (event.day_num * 1440) + (event.fire_time.hour * 60) + event.fire_time.minute
            )
        )
    else:
        raise ValueError("Unexpected event_interpretation '%s'" % handler.event_interpretation)


def get_recipients(handler):
    if handler.recipient == RECIPIENT_CASE:
        return [(CaseScheduleInstanceMixin.RECIPIENT_TYPE_SELF, None)]
    elif handler.recipient == RECIPIENT_OWNER:
        return [(CaseScheduleInstanceMixin.RECIPIENT_TYPE_CASE_OWNER, None)]
    else:
        raise ValueError("Unexpected recipient: '%s'" % handler.recipient)


def migrate_rule(handler, schedule):
    rule = AutomaticUpdateRule.objects.create(
        domain=handler.domain,
        name=handler.nickname,
        case_type=handler.case_type,
        active=True,
        deleted=False,
        filter_on_server_modified=False,
        server_modified_boundary=None,
        migrated=True,
        workflow=AutomaticUpdateRule.WORKFLOW_SCHEDULING,
    )
    if not handler.start_property:
        raise ValueError("Expected start_property")

    if not (handler.start_property == '_id' and handler.start_match_type == MATCH_ANY_VALUE):
        if handler.start_match_type == MATCH_ANY_VALUE:
            rule.add_criteria(
                MatchPropertyDefinition,
                property_name=handler.start_property,
                match_type=MatchPropertyDefinition.MATCH_HAS_VALUE,
            )
        elif handler.start_match_type == MATCH_EXACT:
            if not handler.start_value:
                raise ValueError("Expected start_value")

            rule.add_criteria(
                MatchPropertyDefinition,
                property_name=handler.start_property,
                property_value=handler.start_value,
                match_type=MatchPropertyDefinition.MATCH_EQUAL,
            )
        else:
            raise ValueError("Unexpected start_match_type '%s'" % handler.start_match_type)

    rule.add_action(
        CreateScheduleInstanceActionDefinition,
        alert_schedule_id=schedule.schedule_id if isinstance(schedule, AlertSchedule) else None,
        timed_schedule_id=schedule.schedule_id if isinstance(schedule, TimedSchedule) else None,
        recipients=get_recipients(handler),
    )
    return rule


def migrate_simple_alert_schedule(handler):
    return AlertSchedule.create_simple_alert(
        handler.domain,
        get_content(handler, handler.events[0]),
        extra_options=get_extra_scheduling_options(handler),
    )


def migrate_custom_alert_schedule(handler):
    return AlertSchedule.create_custom_alert(
        handler.domain,
        [(get_event(handler, event), get_content(handler, event)) for event in handler.events],
        extra_options=get_extra_scheduling_options(handler),
    )


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('domain')
        parser.add_argument(
            "--check",
            action="store_true",
            dest="check",
            default=False,
            help="Check if the migration can proceed but don't make changes",
        )

    def get_rule_migration_function(self, handler):
        if handler.start_condition_type != CASE_CRITERIA:
            return None

        if handler.start_match_type in (MATCH_EXACT, MATCH_REGEX) and not handler.start_value:
            return None

        if handler.start_match_type not in (MATCH_EXACT, MATCH_ANY_VALUE):
            return None

        if not handler.start_property or '/' in handler.start_property:
            return None

        if handler.start_date:
            return None

        if handler.until:
            return None

        return migrate_rule

    def get_rule_schedule_migration_function(self, handler):
        if handler.start_condition_type != CASE_CRITERIA:
            return None

        if handler.method not in (METHOD_SMS, METHOD_EMAIL):
            return None

        if handler.include_child_locations:
            return None

        if handler.custom_content_handler:
            return None

        if handler.recipient not in (
            RECIPIENT_OWNER,
            RECIPIENT_CASE,
        ):
            return None

        if handler.user_data_filter:
            return None

        if (
            handler.event_interpretation == EVENT_AS_OFFSET and
            handler.start_date is None and
            handler.start_offset == 0 and
            handler.start_day_of_week == DAY_ANY and
            handler.max_iteration_count == 1
        ):
            if (
                len(handler.events) == 1 and
                handler.events[0].day_num == 0 and
                handler.events[0].fire_time in (time(0, 0), time(0, 1))
            ):
                return migrate_simple_alert_schedule
            else:
                return migrate_custom_alert_schedule

        return None

    def get_migrator(self, handler):
        if handler.locked:
            return None

        if handler.use_today_if_start_date_is_blank and handler.active and handler.start_date:
            return None

        for event in handler.events:
            if event.fire_time and event.fire_time.second != 0:
                return None

        if handler.reminder_type == REMINDER_TYPE_DEFAULT:
            rule_migration_function = self.get_rule_migration_function(handler)
            schedule_migration_function = self.get_rule_schedule_migration_function(handler)
            if rule_migration_function and schedule_migration_function:
                return CaseReminderHandlerMigrator(handler, rule_migration_function, schedule_migration_function)

            return None
        elif handler.reminder_type == REMINDER_TYPE_ONE_TIME:
            return None

    def should_skip(self, handler):
        return handler.reminder_type in (REMINDER_TYPE_KEYWORD_INITIATED, REMINDER_TYPE_SURVEY_MANAGEMENT)

    def migration_already_done(self, domain_obj):
        if domain_obj.uses_new_reminders:
            print("'%s' already uses new reminders, nothing to do" % domain_obj.name)
            return True

        return False

    def ensure_migration_flag_enabled(self, domain):
        while not REMINDERS_MIGRATION_IN_PROGRESS.enabled(domain):
            moves.input("Please enable REMINDERS_MIGRATION_IN_PROGRESS for '%s' and hit enter..." % domain)

        print("REMINDERS_MIGRATION_IN_PROGRESS enabled for %s" % domain)

    def get_handlers_to_migrate(self, domain):
        handlers = CaseReminderHandler.view(
            'reminders/handlers_by_domain_case_type',
            startkey=[domain],
            endkey=[domain, {}],
            include_docs=True
        ).all()

        return [handler for handler in handlers if not self.should_skip(handler)]

    def get_migrators(self, handlers):
        migrators = []
        cannot_be_migrated = []
        for handler in handlers:
            migrator = self.get_migrator(handler)
            if migrator:
                migrators.append(migrator)
            else:
                cannot_be_migrated.append(handler)

        if cannot_be_migrated:
            print("The following configurations can't be migrated:")
            for handler in cannot_be_migrated:
                print("%s %s" % (handler._id, handler.reminder_type))

        return migrators, cannot_be_migrated

    def migrate_handlers(self, migrators):
        for migrator in migrators:
            migrator.migrate()
            migrator.migrate_schedule_instances()

    def confirm_migration_begin(self):
        while True:
            answer = moves.input("Are you sure you want to start the migration? y/n ").lower()
            if answer == 'y':
                return True
            elif answer == 'n':
                return False

    def handle(self, domain, **options):
        check_only = options['check']
        domain_obj = Domain.get_by_name(domain)

        if self.migration_already_done(domain_obj):
            return

        if not check_only:
            self.ensure_migration_flag_enabled(domain)

        handlers = self.get_handlers_to_migrate(domain)
        migrators, cannot_be_migrated = self.get_migrators(handlers)
        if cannot_be_migrated:
            return

        print("Migration can proceed")

        if check_only:
            return

        if not self.confirm_migration_begin():
            print("Migrated halted")
            return

        self.migrate_handlers(migrators)