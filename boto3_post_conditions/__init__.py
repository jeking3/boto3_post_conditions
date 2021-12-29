# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules

__all__ = (
    "PostConditionEnforcer",
    "PostConditionError",
    "PostConditionNotSatisfiedError",
)

from .enforcer import PostConditionEnforcer
from .exceptions import PostConditionError
from .exceptions import PostConditionNotSatisfiedError

# import each service module to register available post-condition
# check logic with the PortConditionEnforcer; consumers will then
# register their boto3 clients with the enforcer to inject the
# post-condition hooks
services_dir = Path(__file__).parent / "services"
for info in iter_modules([str(services_dir)]):
    if not info.name.startswith("_"):  # pragma: no cover
        import_module(f"{__name__}.services.{info.name}")
