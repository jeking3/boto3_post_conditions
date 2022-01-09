# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 - 2022 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from . import ensure_tags_realized
from . import ensure_tags_unrealized
from .. import PostConditionEnforcer
from .. import PostConditionNotSatisfiedError

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient
else:
    SSMClient = object


@PostConditionEnforcer
def AddTagsToResource(client: SSMClient, *args, **kwargs):
    requested_tags = kwargs["context"]["api_params"].get("Tags", [])
    response = client.list_tags_for_resource(
        ResourceId=kwargs["context"]["api_params"]["ResourceId"],
        ResourceType="Parameter",
    )
    ensure_tags_realized(
        requested_tags,
        response["TagList"],
        PostConditionNotSatisfiedError(
            "ssm",
            "AddTagsToResource",
            "ListTagsForResource",
            "tag changes are still pending realization",
        ),
    )


@PostConditionEnforcer
def DeleteParameter(client: SSMClient, *args, **kwargs):
    try:
        client.get_parameter(Name=kwargs["context"]["api_params"]["Name"])
        raise PostConditionNotSatisfiedError(
            "ssm",
            "DeleteParameter",
            "GetParameter",
            "deletion is still pending realization",
        )
    except ClientError as ex:
        if ex.response["Error"]["Code"] == "ParameterNotFound":
            return
        raise  # pragma: no cover


@PostConditionEnforcer
def DeleteParameters(client: SSMClient, *args, **kwargs):
    deleted_names = sorted(kwargs["context"]["api_params"]["Names"])
    response = client.get_parameters(Names=deleted_names)
    if deleted_names != sorted(response["InvalidParameters"]):
        raise PostConditionNotSatisfiedError(
            "ssm",
            "DeleteParameters",
            "GetParameters",
            "deletion is still pending realization",
        )


@PostConditionEnforcer
def PutParameter(client: SSMClient, *args, **kwargs):
    try:
        # this may raise ClientError with ParameterNotFound
        client.get_parameter(Name=kwargs["context"]["api_params"]["Name"])

        # assumption: one can only add tags with `Tags`
        requested_tags = kwargs["context"]["api_params"].get("Tags", [])
        if requested_tags:
            # this may raise ClientError with InvalidResourceId if the
            # Resource and Tag Manager hasn't realized the parameter yet
            response = client.list_tags_for_resource(
                ResourceId=kwargs["context"]["api_params"]["Name"],
                ResourceType="Parameter",
            )
            ensure_tags_realized(
                requested_tags,
                response["TagList"],
                PostConditionNotSatisfiedError(
                    "ssm",
                    "PutParameter",
                    "ListTagsForResource",
                    "tag changes are still pending realization",
                ),
            )

    except ClientError as ex:
        if ex.response["Error"]["Code"] == "ParameterNotFound":
            raise PostConditionNotSatisfiedError(
                "ssm",
                "PutParameter",
                "GetParameter",
                "parameter changes are still pending realization",
                original_error=ex,
            )
        elif ex.response["Error"]["Code"] == "InvalidResourceId":
            raise PostConditionNotSatisfiedError(
                "ssm",
                "PutParameter",
                "ListTagsForResource",
                "tag changes are still pending realization",
                original_error=ex,
            )
        raise  # pragma: no cover


@PostConditionEnforcer
def RemoveTagsFromResource(client: SSMClient, *args, **kwargs):
    requested_tag_keys = kwargs["context"]["api_params"]["TagKeys"]
    response = client.list_tags_for_resource(
        ResourceId=kwargs["context"]["api_params"]["ResourceId"],
        ResourceType="Parameter",
    )
    ensure_tags_unrealized(
        requested_tag_keys,
        response["TagList"],
        PostConditionNotSatisfiedError(
            "ssm",
            "RemoveTagsFromResource",
            "ListTagsForResource",
            "tag deletions are still pending realization",
        ),
    )
