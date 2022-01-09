# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 - 2022 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
import logging

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from moto.secretsmanager import mock_secretsmanager

from boto3_post_conditions import PostConditionEnforcer
from tests import access_denied
from tests import PostConditionTestCase


@mock_secretsmanager
class EnforcerTest(PostConditionTestCase):
    def count_handlers_for_service(self, client: BaseClient) -> int:
        service = client.meta.service_model.service_name
        handlers = client.meta.events._emitter._handlers._root["children"]["after-call"]["children"]  # type: ignore
        try:
            return len(handlers[service]["children"])
        except KeyError:
            return 0

    def test_register_ok_loads_once(self) -> None:
        client = boto3.client("ssm")
        events_before = self.count_handlers_for_service(client)
        PostConditionEnforcer.register(client)
        events_after = self.count_handlers_for_service(client)
        self.assertLess(events_before, events_after)
        self.assertGreater(events_after - events_before, 1)

        # this will end up re-using previously imported service enforcers
        client2 = boto3.client("ssm")
        events_before = self.count_handlers_for_service(client2)
        PostConditionEnforcer.register(client2)
        events_after = self.count_handlers_for_service(client2)
        self.assertLess(events_before, events_after)
        self.assertGreater(events_after - events_before, 1)

    def test_register_only_one_call_and_logger(self) -> None:
        client = boto3.client("ssm")
        logger = logging.getLogger(__name__)
        events_before = self.count_handlers_for_service(client)
        with self.assertLogs(logger, logging.DEBUG):
            PostConditionEnforcer.register(client, call="PutParameter", logger=logger)
        events_after = self.count_handlers_for_service(client)
        self.assertLess(events_before, events_after)
        self.assertEqual(events_after - events_before, 1)

    def test_register_unsupported(self) -> None:
        client = boto3.client("s3")
        with self.assertRaises(ImportError):
            PostConditionEnforcer.register(client)

    def test_unexpected_error(self) -> None:
        """
        The common PostConditionEnforcer code will not engage on an error
        condition (any http response >= 300).  Only success responses will
        cause any injected post-condition enforcement to engage.
        """
        client = boto3.client("secretsmanager")
        client.meta.events.register(
            event_name="before-send.secrets-manager.CreateSecret",
            handler=access_denied,
            unique_id="test_unexpected_error",
        )
        PostConditionEnforcer.register(client)
        with self.assertRaises(ClientError) as ce:
            client.create_secret(
                Name="test_unexpected_error",
                SecretString="test_unexpected_error_data",
            )
        self.assertEqual(
            ce.exception.response["Error"]["Code"], "AccessDeniedException"
        )
        self.sleep_mock.assert_not_called()

    def _extract_client_and_params_not_found(self) -> None:
        """If not called in the context of a botocore stack, it should throw."""
        self.assertRaises(
            NotImplementedError, PostConditionEnforcer._extract_client_and_params()
        )
