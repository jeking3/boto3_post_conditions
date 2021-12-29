# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
from typing import Dict
from typing import List

from boto3_post_conditions import PostConditionNotSatisfiedError


def ensure_tags_realized(
    request_aws_tags: List[Dict[str, str]],
    # each subsystem declares a different response type
    response_aws_tags: List,
    exception_to_raise: PostConditionNotSatisfiedError,
) -> None:
    """
    Ensures all tags in the request are in the response.
    """
    request_dict_tags = {item["Key"]: item["Value"] for item in request_aws_tags}
    response_dict_tags = {item["Key"]: item["Value"] for item in response_aws_tags}
    for key, value in request_dict_tags.items():
        if response_dict_tags.get(key, None) != value:
            raise exception_to_raise


def ensure_tags_unrealized(
    request_aws_tagkeys: List[str],
    # each subsystem declares a different response type
    response_aws_tags: List,
    exception_to_raise: PostConditionNotSatisfiedError,
) -> None:
    """
    Ensures all tags to be removed in the request are not in the response.
    """
    response_dict_tags = {item["Key"]: item["Value"] for item in response_aws_tags}
    for key in request_aws_tagkeys:
        if key in response_dict_tags:
            raise exception_to_raise
