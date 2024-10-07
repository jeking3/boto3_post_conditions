# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 - 2022 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
import boto3
import vcr
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError
from moto.core.botocore_stubber import MockRawResponse
from moto.ssm import mock_ssm

from boto3_post_conditions import PostConditionEnforcer
from tests import intercept
from tests import PostConditionTestCase
from tests import RepeatingEventHandler

my_vcr = vcr.VCR(
    cassette_library_dir="tests/services/recordings/ssm",
    filter_headers=["Authorization"],
)


class ParameterEventuallyCreatedEventHandler(RepeatingEventHandler):
    """
    Simulates DescribeParameter cannot see it immediately after PutParameter.
    """

    def handle(self, request, event_name, **kwargs):
        return AWSResponse(
            request.url,
            400,
            {},
            MockRawResponse('{"__type":"ParameterNotFound","Message":"Not there"}'),
        )


class ParameterEventuallyDeletedEventHandler(RepeatingEventHandler):
    def handle(self, request, event_name, **kwargs):
        return AWSResponse(
            request.url,
            200,
            {},
            MockRawResponse('{"ARN":"foo:bar:sam","Name":"Yes"}'),
        )


class ParametersEventuallyDeletedEventHandler(RepeatingEventHandler):
    def handle(self, request, event_name, **kwargs):
        return AWSResponse(
            request.url,
            200,
            {},
            MockRawResponse(
                '{"InvalidParameters":["test_delete_parameters_1"],"Parameters":[{"Name":"test_delete_parameters_2"}]}'
            ),
        )


class ParameterEventuallyTaggedEventHandler(RepeatingEventHandler):
    """
    Simulates it taking time for the tags to align.

    On the first call it returns an InvalidResourceId error.
    On the second call it returns a tag list that is empty.
    """

    def handle(self, request, event_name, **kwargs):
        if self.calls_left == 1:
            return AWSResponse(
                request.url,
                400,
                {},
                MockRawResponse('{"__type":"InvalidResourceId","Message":"Not there"}'),
            )
        else:
            return AWSResponse(
                request.url,
                200,
                {},
                MockRawResponse('{"TagList":[]}'),
            )


class ParameterEventuallyUntaggedEventHandler(RepeatingEventHandler):
    def handle(self, request, event_name, **kwargs):
        return AWSResponse(
            request.url,
            200,
            {},
            MockRawResponse('{"TagList":[{"Key":"foo","Value":"bar"}]}'),
        )


class SSMPostConditionTestCase(PostConditionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = boto3.client("ssm")
        PostConditionEnforcer.register(self.client)


@mock_ssm
class SSMTest(SSMPostConditionTestCase):
    def test_add_tags_to_resource(self) -> None:
        param_name = "test_add_tags_to_resource"
        self.client.put_parameter(Name=param_name, Type="String", Value="value")
        eventually_tagged_handler = ParameterEventuallyTaggedEventHandler()
        try:
            with intercept(
                self.client,
                "before-send.ssm.ListTagsForResource",
                eventually_tagged_handler,
            ):
                self.client.add_tags_to_resource(
                    ResourceId=param_name,
                    ResourceType="Parameter",
                    Tags=[dict(Key="foo", Value="bar")],
                )
                self.assertEqual(eventually_tagged_handler.calls_left, 0)
        finally:  # leave moto clean on error
            self.client.delete_parameters(Names=[param_name])

    def test_delete_parameter(self) -> None:
        param_name = "test_delete_parameter"
        self.client.put_parameter(Name=param_name, Type="String", Value="value")
        eventually_deleted_handler = ParameterEventuallyDeletedEventHandler()
        try:
            with intercept(
                self.client, "before-send.ssm.GetParameter", eventually_deleted_handler
            ):
                self.client.delete_parameter(Name=param_name)
                self.assertEqual(eventually_deleted_handler.calls_left, 0)
        finally:  # leave moto clean on error
            self.client.delete_parameters(Names=[param_name])

    def test_delete_parameters(self) -> None:
        self.client.put_parameter(
            Name="test_delete_parameters_1", Type="String", Value="value"
        )
        self.client.put_parameter(
            Name="test_delete_parameters_2", Type="String", Value="value"
        )
        eventually_deleted_handler = ParametersEventuallyDeletedEventHandler()
        try:
            with intercept(
                self.client, "before-send.ssm.GetParameters", eventually_deleted_handler
            ):
                self.client.delete_parameters(
                    Names=["test_delete_parameters_1", "test_delete_parameters_2"]
                )
                self.assertEqual(eventually_deleted_handler.calls_left, 0)
        finally:  # leave moto clean on error
            self.client.delete_parameters(
                Names=["test_delete_parameters_1", "test_delete_parameters_2"]
            )

    def test_put_parameter_with_tag(self) -> None:
        param_name = "test_put_parameter_with_tag"
        eventually_created_handler = ParameterEventuallyCreatedEventHandler()
        eventually_tagged_handler = ParameterEventuallyTaggedEventHandler(times=2)
        try:
            with intercept(
                self.client, "before-send.ssm.GetParameter", eventually_created_handler
            ):
                with intercept(
                    self.client,
                    "before-send.ssm.ListTagsForResource",
                    eventually_tagged_handler,
                ):
                    self.client.put_parameter(
                        Name=param_name,
                        Type="String",
                        Value="value",
                        Tags=[dict(Key="foo", Value="bar")],
                    )
                    self.assertEqual(eventually_created_handler.calls_left, 0)
                    self.assertEqual(eventually_tagged_handler.calls_left, 0)
        finally:  # leave moto clean on error
            self.client.delete_parameters(Names=[param_name])

    def test_put_parameter_without_tag(self) -> None:
        param_name = "test_put_parameter_without_tag"
        eventually_created_handler = ParameterEventuallyCreatedEventHandler()
        eventually_tagged_handler = ParameterEventuallyTaggedEventHandler(times=2)
        try:
            with intercept(
                self.client, "before-send.ssm.GetParameter", eventually_created_handler
            ):
                with intercept(
                    self.client,
                    "before-send.ssm.ListTagsForResource",
                    eventually_tagged_handler,
                ):
                    self.client.put_parameter(
                        Name=param_name, Type="String", Value="value"
                    )
                    self.assertEqual(eventually_created_handler.calls_left, 0)
                    self.assertEqual(eventually_tagged_handler.calls_left, 2)
        finally:  # leave moto clean on error
            self.client.delete_parameters(Names=[param_name])

    def test_remove_tags_from_resource(self) -> None:
        param_name = "test_remove_tags_from_resource"
        self.client.put_parameter(
            Name=param_name,
            Type="String",
            Value="value",
            Tags=[dict(Key="foo", Value="bar")],
        )
        eventually_untagged_handler = ParameterEventuallyUntaggedEventHandler()
        try:
            with intercept(
                self.client,
                "before-send.ssm.ListTagsForResource",
                eventually_untagged_handler,
            ):
                self.client.remove_tags_from_resource(
                    ResourceId=param_name,
                    ResourceType="Parameter",
                    TagKeys=["foo"],
                )
                self.assertEqual(eventually_untagged_handler.calls_left, 0)
        finally:  # leave moto clean on error
            self.client.delete_parameters(Names=[param_name])


class SSMIntegrationTest(SSMPostConditionTestCase):
    @my_vcr.use_cassette()
    def test_ssm_integration(self) -> None:
        """This demonstrates an actual AWS integration without the need for retry logic."""
        try:
            # the test fixture obtained a ssm client and registered it with boto3_post_conditions

            # add a novel parameter
            param_name = "b3pc_test_ssm_integration"
            self.client.put_parameter(
                Name=param_name,
                Type="String",
                Value="value1",
                Tags=[dict(Key="foo", Value="bar")],
            )

            # without boto3_post_conditions you would need to wrap the next call
            # in an exception handler to catch the InvalidResourceId that can happen
            # due to eventualy consistency
            tags = self.client.list_tags_for_resource(
                ResourceType="Parameter", ResourceId=param_name
            )
            self.assertEqual(tags["TagList"], [dict(Key="foo", Value="bar")])

            # without boto3_post_conditions you would need to wrap the next call
            # in an exception handler to catch the ParameterNotFound that can happen
            # due to eventualy consistency - yes, it's possible to put a parameter
            # then be unable to get the parameter right away - isn't eventual consistency fun?
            value = self.client.get_parameter(Name=param_name, WithDecryption=False)
            self.assertEqual(value["Parameter"]["Value"], "value1")

            # update the value
            self.client.put_parameter(
                Name=param_name, Type="String", Value="value2", Overwrite=True
            )

            # without boto3_post_conditions the next call could return the old value,
            # however enforcing post-conditions ensures you can read what you wrote
            value = self.client.get_parameter(Name=param_name, WithDecryption=False)
            self.assertEqual(value["Parameter"]["Value"], "value2")

            # use a tight loop to delete, re-create the same value
            for loop in range(3):
                # delete the parameter
                self.client.delete_parameter(Name=param_name)

                # deletions take time to realize, so it is possible for delete_parameter
                # to return success but then get may still see it, or put may raise an
                # exception for ParameterAlreadyExists; however with boto3_post_conditions
                # enforcing the delete_parameter post-condition, those won't happen
                self.client.put_parameter(
                    Name=param_name, Type="String", Value=f"value{3 + loop}"
                )
                value = self.client.get_parameter(Name=param_name, WithDecryption=False)
                self.assertEqual(value["Parameter"]["Value"], f"value{3 + loop}")

        finally:
            # clean up safely
            try:
                self.client.delete_parameter(Name=param_name)
            except ClientError as ex:
                if ex.response["Error"]["Code"] != "ParameterNotFound":
                    raise
