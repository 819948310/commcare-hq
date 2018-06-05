from __future__ import absolute_import
from __future__ import unicode_literals

import jsonfield
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class RequestLog(models.Model):
    """
    Store API requests and responses to analyse errors and keep an audit trail
    """
    domain = models.CharField(max_length=126, db_index=True)  # 126 seems to be a popular length
    timestamp = models.DateTimeField(auto_now_add=True)
    log_level = models.IntegerField(null=True)
    request_method = models.CharField(max_length=12)
    request_url = models.CharField(max_length=255)
    request_headers = jsonfield.JSONField(blank=True)
    request_params = jsonfield.JSONField(blank=True)
    request_body = jsonfield.JSONField(
        blank=True, null=True,  # NULL for GET, but POST can take an empty body
        dump_kwargs={'cls': DjangoJSONEncoder, 'separators': (',', ':')}  # Use DjangoJSONEncoder for dates, etc.
    )
    request_error = models.TextField(null=True)
    response_status = models.IntegerField(null=True)
    response_body = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'dhis2_jsonapilog'

    @staticmethod
    def unpack_request_args(request_method, args, kwargs):
        params = kwargs.pop('params', '')
        json_data = kwargs.pop('json', '')
        data = kwargs.pop('data', json_data)  # Don't bother trying to
        # cast as a dict. `data` will be rendered as prettified JSON if
        # possible, regardless of whether it's a dict or a string here.
        if args:
            if request_method == 'GET':
                params = args[0]
            elif request_method == 'PUT':
                data = args[0]
            elif request_method == 'POST':
                # requests.post() allows `data` and `json` to be given
                # as positional arguments, but ignores `json` if `data`
                # has a value.
                data = args[1] if len(args) == 2 and not args[0] else args[0]
        headers = kwargs.pop('headers', {})
        return params, data, headers

    @staticmethod
    def log(log_level, domain_name, request_error, response_status, response_body,
            method_func, request_url, *args, **kwargs):
        # The order of arguments is important: `method_func`,
        # `request_url` and `*args` are the Requests method and its
        # positional arguments. Having these at the end of this
        # method's args allows us to call `log` with `*args, **kwargs`
        request_method = method_func.__name__.upper()
        params, data, headers = RequestLog.unpack_request_args(request_method, args, kwargs)
        RequestLog.objects.create(
            domain=domain_name,
            log_level=log_level,
            request_method=request_method,
            request_url=request_url,
            request_headers=headers,
            request_params=params,
            request_body=data,
            request_error=request_error,
            response_status=response_status,
            response_body=response_body,
        )
