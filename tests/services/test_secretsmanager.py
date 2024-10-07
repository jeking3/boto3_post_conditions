# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 - 2022 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
import boto3
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError
from moto.core.botocore_stubber import MockRawResponse
from moto.secretsmanager import mock_secretsmanager

from boto3_post_conditions import PostConditionEnforcer
from tests import access_denied
from tests import intercept
from tests import PostConditionTestCase
from tests import RepeatingEventHandler


class SecretEventuallyCreatedEventHandler(RepeatingEventHandler):
    """
    On the first attempt to pretends the secret is not there.
    On the second attempt it responds without tags.
    Assuming the caller uses (times=2) when initializing, it bows out after that.
    """

    def handle(self, request, event_name, **kwargs):
        if self.calls_left == 1:
            return AWSResponse(
                request.url,
                400,
                {},
                MockRawResponse(
                    '{"__type":"ResourceNotFoundException","Message":"Not there"}'
                ),
            )
        else:
            return AWSResponse(
                request.url,
                200,
                {},
                MockRawResponse('{"ARN":"foo:bar:sam","Name":"Yes"}'),
            )


class SecretEventuallyDeletedEventHandler(RepeatingEventHandler):
    """
    Returns something that looks like it still exists, but has no tags.
    The delete test relies on the existence, the tag test relies on the lack of tags.
    """

    def handle(self, request, event_name, **kwargs):
        return AWSResponse(
            request.url,
            200,
            {},
            MockRawResponse('{"ARN":"foo:bar:sam","Name":"Yes"}'),
        )


class SecretEventuallyUntaggedEventHandler(RepeatingEventHandler):
    def handle(self, request, event_name, **kwargs):
        return AWSResponse(
            request.url,
            200,
            {},
            MockRawResponse(
                '{"ARN":"foo:bar:sam","Name":"Yes","Tags":[{"Key":"foo","Value":"bar"}]}'
            ),
        )


class SSMPostConditionTestCase(PostConditionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = boto3.client("secretsmanager")
        PostConditionEnforcer.register(self.client)


@mock_secretsmanager
class SecretsManagerTest(SSMPostConditionTestCase):
    def test_create_secret(self) -> None:
        """
        On the first post-condition check we get ResourceNotFoundException.
        On the second post-condition check we get back data without tags.
        On the third post-condition check we get back what we expect.
        """
        secret_id = "test_create_secret"  # nosec
        eventually_created_handler = SecretEventuallyCreatedEventHandler(times=2)
        try:
            with intercept(
                self.client,
                "before-send.secretsmanager.DescribeSecret",
                eventually_created_handler,
            ):
                result = self.client.create_secret(
                    Name=secret_id,
                    SecretString="test_create_secret_data",
                    Tags=[dict(Key="foo", Value="bar")],
                )
                secret_id = result["ARN"]
                self.assertEqual(eventually_created_handler.calls_left, 0)
        finally:  # leave moto clean on error
            self.client.delete_secret(
                SecretId=secret_id, ForceDeleteWithoutRecovery=True
            )

    def test_create_secret_unexpected_error(self) -> None:
        secret_id = "test_create_secret_unexpected_error"  # nosec
        with intercept(
            self.client, "before-send.secretsmanager.DescribeSecret", access_denied
        ):
            with self.assertRaises(ClientError) as ce:
                self.client.create_secret(
                    Name=secret_id,
                    SecretString="test_create_secret_unexpected_error_data",
                )
            self.assertEqual(
                ce.exception.response["Error"]["Code"], "AccessDeniedException"
            )

    def test_delete_secret(self) -> None:
        secret_id = "test_delete_secret"  # nosec
        result = self.client.create_secret(
            Name=secret_id,
            SecretString="test_delete_secret_data",
        )
        secret_id = result["ARN"]

        # returns 200 content without Tags many times, like delete is taking a while
        eventually_deleted_handler = SecretEventuallyDeletedEventHandler(times=6)

        try:
            with intercept(
                self.client,
                "before-send.secretsmanager.DescribeSecret",
                eventually_deleted_handler,
            ):
                self.client.delete_secret(
                    SecretId=secret_id, ForceDeleteWithoutRecovery=True
                )
                self.assertEqual(eventually_deleted_handler.calls_left, 0)
                secret_id = ""  # nosec
        finally:  # leave moto clean on error
            if secret_id:
                self.client.delete_secret(
                    SecretId=secret_id, ForceDeleteWithoutRecovery=True
                )

    def test_tag_resource(self) -> None:
        secret_id = "test_tag_resource"  # nosec
        result = self.client.create_secret(
            Name=secret_id,
            SecretString="test_tag_resource_data",
        )
        secret_id = result["ARN"]

        # returns 200 content without Tags once, works well for this case
        eventually_tagged_handler = SecretEventuallyDeletedEventHandler()

        try:
            with intercept(
                self.client,
                "before-send.secretsmanager.DescribeSecret",
                eventually_tagged_handler,
            ):
                self.client.tag_resource(
                    SecretId=secret_id, Tags=[dict(Key="foo", Value="bar")]
                )
                self.assertEqual(eventually_tagged_handler.calls_left, 0)
        finally:  # leave moto clean on error
            self.client.delete_secret(
                SecretId=secret_id, ForceDeleteWithoutRecovery=True
            )

    def test_untag_resource(self) -> None:
        secret_id = "test_untag_resource"  # nosec
        result = self.client.create_secret(
            Name=secret_id,
            SecretString="test_untag_resource_data",
        )
        secret_id = result["ARN"]

        # this returns a response with tags, once, then disables itself
        eventually_untagged_handler = SecretEventuallyUntaggedEventHandler()

        try:
            with intercept(
                self.client,
                "before-send.secretsmanager.DescribeSecret",
                eventually_untagged_handler,
            ):
                self.client.untag_resource(SecretId=secret_id, TagKeys=["foo"])
                self.assertEqual(eventually_untagged_handler.calls_left, 0)
        finally:  # leave moto clean on error
            self.client.delete_secret(
                SecretId=secret_id, ForceDeleteWithoutRecovery=True
            )
