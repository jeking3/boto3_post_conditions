# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 - 2022 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
import os
from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from typing import Generator
from unittest import TestCase
from unittest.mock import patch

from botocore.awsrequest import AWSResponse
from botocore.client import BaseClient
from moto.core.botocore_stubber import MockRawResponse


class PostConditionTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        # vcrpy has no facility to identify if it is in recording mode;
        # set RECORDING when you are recording until there is a better solution

        if "RECORDING" in os.environ:
            self.assertIn("AWS_ACCOUNT_ID", os.environ)
            self.assertIn("AWS_ACCESS_KEY_ID", os.environ)
            self.assertIn("AWS_DEFAULT_REGION", os.environ)
            self.assertIn("AWS_SECRET_ACCESS_KEY", os.environ)
        else:
            # playback: provide (slightly) silly values so it is easy to run tests
            os.environ["AWS_ACCOUNT_ID"] = "123456789012"
            os.environ["AWS_ACCESS_KEY_ID"] = "foo"
            os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
            os.environ["AWS_SECRET_ACCESS_KEY"] = "bar"  # nosec
            self.sleep_patch = patch("retry.api.time.sleep", autospec=True)
            self.sleep_mock = self.sleep_patch.start()

    def tearDown(self) -> None:
        if "RECORDING" not in os.environ:
            self.sleep_patch.stop()

        super().tearDown()


class RepeatingEventHandler(ABC):
    """
    Injects an alternate response for a limited number of times.
    """

    def __init__(self, times: int = 1) -> None:
        self.calls_left = times

    def __call__(self, request, event_name, **kwargs):
        if self.calls_left == 0:
            return None
        self.calls_left -= 1
        return self.handle(request, event_name, **kwargs)

    @abstractmethod
    def handle(self, request, event_name, **kwargs):
        raise NotImplementedError()


def access_denied(request, event_name, **kwargs):
    return AWSResponse(
        request.url,
        403,
        {},
        MockRawResponse(
            '{"__type":"AccessDeniedException","Message":"User: ... '
            'is not authorized to perform: secretsmanager:ListTagsForResource on resource: ..."}'
        ),
    )


@contextmanager
def intercept(
    client: BaseClient, event_name: str, handler: RepeatingEventHandler
) -> Generator:
    client.meta.events.register(event_name=event_name, handler=handler)
    try:
        yield
    finally:
        client.meta.events.unregister(event_name=event_name, handler=handler)
