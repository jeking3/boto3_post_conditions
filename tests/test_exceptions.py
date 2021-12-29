# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
from boto3_post_conditions import PostConditionNotSatisfiedError
from tests import PostConditionTestCase


class ExceptionsTest(PostConditionTestCase):
    def test_not_satisfied(self) -> None:
        uut = PostConditionNotSatisfiedError(
            service="secretsmanager",
            original_call="TagResource",
            condition_check_call="DescribeSecret",
            condition_not_met="new tags not realized yet",
        )

        errmsg = str(uut)
        self.assertIn("PostConditionNotSatisfiedException", errmsg)
        self.assertIn("DescribeSecret", errmsg)
        self.assertIn("significant processing delays", errmsg)
