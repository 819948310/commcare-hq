from __future__ import absolute_import
import json
import traceback
from datetime import datetime, timedelta
from dateutil.parser import parse
from django.conf import settings
import math
from django.db import models
from django.db.models.aggregates import Count
from jsonfield.fields import JSONField

from pillowtop.feed.couch import change_from_couch_row
from pillowtop.feed.interface import ChangeMeta

ERROR_MESSAGE_LENGTH = 512


def _get_extra_args(limit, reduce, skip):
    extra_args = dict()
    if not reduce and limit is not None:
            extra_args.update(
                limit=limit,
                skip=skip
            )
    return extra_args


def path_from_object(obj):
    path = "{0}.{1}".format(obj.__class__.__module__, obj.__class__.__name__)
    return path


class PillowError(models.Model):
    doc_id = models.CharField(max_length=255, null=False, db_index=True)
    pillow = models.CharField(max_length=255, null=False, db_index=True)
    date_created = models.DateTimeField()
    date_last_attempt = models.DateTimeField()
    total_attempts = models.IntegerField(default=0)
    error_type = models.CharField(max_length=255, null=True, db_index=True)
    error_traceback = models.TextField(null=True)
    change_metadata = JSONField(null=True)

    @property
    def change_object(self):
        change = change_from_couch_row({'id': self.doc_id})
        if self.change_metadata:
            change.metadata = ChangeMeta.wrap(self.change_metadata)
        change.document = None
        return change

    class Meta(object):
        app_label = 'pillow_retry'
        unique_together = ('doc_id', 'pillow',)

    @classmethod
    def get_or_create(cls, change_metadata, pillow):
        doc_id = change_metadata.document_id
        try:
            error = cls.objects.get(doc_id=doc_id, pillow=pillow.pillow_id)
        except cls.DoesNotExist:
            now = datetime.utcnow()
            error = PillowError(
                doc_id=doc_id,
                pillow=pillow.pillow_id,
                date_created=now,
                date_last_attempt=change_metadata.date_last_attempt,
                total_attempts=change_metadata.attempts,
                error_type=change_metadata.last_error_type,
                error_traceback=change_metadata.last_error_traceback,
                change_metadata=change_metadata.to_json(),
            )

        return error

    @classmethod
    def get_errors_to_process(cls, utcnow, limit=None, skip=0, fetch_full=False):
        """
        Get errors according the following rules:

            date_next_attempt <= utcnow
            AND
            (
                total_attempts <= multi_attempt_cutoff & current_attempt <= max_attempts
                OR
                total_attempts > multi_attempt_cutoff & current_attempt 0
            )

        where:
        * multi_attempt_cutoff = settings.PILLOW_RETRY_MULTI_ATTEMPTS_CUTOFF
        * max_attempts = settings.PILLOW_RETRY_QUEUE_MAX_PROCESSING_ATTEMPTS

        :param utcnow:      The current date and time in UTC.
        :param limit:       Paging limit param.
        :param skip:        Paging skip param.
        :param fetch_full:  If True return the whole PillowError object otherwise return a
                            a dict containing 'id' and 'date_next_attempt' keys.
        """
        max_attempts = settings.PILLOW_RETRY_QUEUE_MAX_PROCESSING_ATTEMPTS
        multi_attempts_cutoff = cls.multi_attempts_cutoff()
        query = PillowError.objects \
            .filter(date_next_attempt__lte=utcnow) \
            .filter(
                models.Q(current_attempt=0) |
                (models.Q(total_attempts__lte=multi_attempts_cutoff) & models.Q(current_attempt__lte=max_attempts))
            )

        # temporarily disable queuing of ConfigurableReportKafkaPillow errors
        query = query.filter(~models.Q(pillow='corehq.apps.userreports.pillow.ConfigurableReportKafkaPillow'))

        if not fetch_full:
            query = query.values('id', 'date_next_attempt')
        if limit is not None:
            return query[skip:skip+limit]
        else:
            return query

    @classmethod
    def multi_attempts_cutoff(cls):
        default = settings.PILLOW_RETRY_QUEUE_MAX_PROCESSING_ATTEMPTS * 3
        return getattr(settings, 'PILLOW_RETRY_MULTI_ATTEMPTS_CUTOFF', default)

    @classmethod
    def get_pillows(cls):
        results = PillowError.objects.values('pillow').annotate(count=Count('pillow'))
        return (p['pillow'] for p in results)

    @classmethod
    def get_error_types(cls):
        results = PillowError.objects.values('error_type').annotate(count=Count('error_type'))
        return (e['error_type'] for e in results)


# Stub models file, also used in tests
from dimagi.ext.couchdbkit import Document


class Stub(Document):
    pass
