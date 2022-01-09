# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 - 2022 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
from typing import Optional

from botocore.exceptions import ClientError


class PostConditionError(ClientError):
    pass


class PostConditionNotSatisfiedError(PostConditionError):
    def __init__(
        self,
        service: str,
        original_call: str,
        condition_check_call: str,
        condition_not_met: str,
        original_error: Optional[ClientError] = None,
    ) -> None:
        super().__init__(
            error_response=dict(
                Error=dict(
                    Code="PostConditionNotSatisfiedException",
                    Message=(
                        f"While enforcing {service} post-conditions for {original_call}: {condition_not_met}.  "
                        f"This indicates significant processing delays are occurring at AWS right now."
                    ),
                )
            ),
            operation_name=condition_check_call,
        )

        self.service = service
        self.original_call = original_call
        self.condition_check_call = condition_check_call
        self.condition_not_met = condition_not_met
        self.original_error = original_error
