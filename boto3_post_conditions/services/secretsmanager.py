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
from boto3_post_conditions import PostConditionEnforcer
from boto3_post_conditions import PostConditionNotSatisfiedError

if TYPE_CHECKING:  # pragma: no cover
    from mypy_boto3_secretsmanager import SecretsManagerClient
else:
    SecretsManagerClient = object


@PostConditionEnforcer
def CreateSecret(client: SecretsManagerClient, *args, **kwargs):
    try:
        response = client.describe_secret(SecretId=kwargs["parsed"]["ARN"])
        ensure_tags_realized(
            kwargs["context"]["api_params"].get("Tags", []),
            response.get("Tags", []),
            PostConditionNotSatisfiedError(
                "secretsmanager",
                "CreateSecret",
                "DescribeSecret",
                "new secret tags pending realization",
            ),
        )
    except ClientError as ex:
        if ex.response["Error"]["Code"] == "ResourceNotFoundException":
            raise PostConditionNotSatisfiedError(
                "secretsmanager",
                "CreateSecret",
                "DescribeSecret",
                "secret not realized",
                original_error=ex,
            )
        raise  # this is covered by a test to prove the pattern works


@PostConditionEnforcer
def DeleteSecret(client: SecretsManagerClient, *args, **kwargs):
    try:
        client.describe_secret(SecretId=kwargs["parsed"]["ARN"])
        raise PostConditionNotSatisfiedError(
            "secretsmanager",
            "DeleteSecret",
            "DescribeSecret",
            "secret deletion pending realization",
        )

    except ClientError as ex:
        if ex.response["Error"]["Code"] == "ResourceNotFoundException":
            return
        raise  # pragma: no cover


@PostConditionEnforcer
def TagResource(client: SecretsManagerClient, *args, **kwargs):
    response = client.describe_secret(
        SecretId=kwargs["context"]["api_params"]["SecretId"]
    )
    ensure_tags_realized(
        kwargs["context"]["api_params"].get("Tags", []),
        response.get("Tags", []),
        PostConditionNotSatisfiedError(
            "secretsmanager",
            "TagResource",
            "DescribeSecret",
            "secret tag changes pending realization",
        ),
    )


@PostConditionEnforcer
def UntagResource(client: SecretsManagerClient, *args, **kwargs):
    response = client.describe_secret(
        SecretId=kwargs["context"]["api_params"]["SecretId"]
    )
    ensure_tags_unrealized(
        kwargs["context"]["api_params"].get("TagKeys", []),
        response.get("Tags", []),
        PostConditionNotSatisfiedError(
            "secretsmanager",
            "UntagResource",
            "DescribeSecret",
            "secret tag deletion pending realization",
        ),
    )
