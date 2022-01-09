# -*- coding: utf-8 -*-
#
# Copyright (C) 2021 - 2022 James E. King III <jking@apache.org>
#
# Distributed under the Apache License, Version 2.0
# See accompanying LICENSE file in this repository or at
# https://www.apache.org/licenses/LICENSE-2.0
#
import inspect
from dataclasses import dataclass
from importlib import import_module
from logging import Logger
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import TYPE_CHECKING

from botocore.client import BaseClient
from retry import retry

from .exceptions import PostConditionNotSatisfiedError

if TYPE_CHECKING:
    from mypy_extensions import KwArg
    from mypy_extensions import VarArg

    # signature of the after_call event handler that is injected
    # TODO: better type for args, kwargs?
    AfterEventHandler = Callable[[BaseClient, VarArg(), KwArg()], None]
else:
    AfterEventHandler = object


@dataclass
class TimeoutSpec:
    """
    Defines how each post-condition enforcement retries until satisfied.

    Each of the services modules defines their own default value for
    timeouts based on anecdotal evidence working with each service.

    The default values implement a backoff strategy whereby the original
    call may block for up to 5 minutes.
    """

    # the number of attempts to make
    attempts: int = 33

    # the initial delay between attempts in seconds
    delay: float = 1

    # the exponential backoff
    backoff: float = 1.1

    # the maximum delay between attempts
    max_delay: float = 10


EventName = str


class PostConditionEnforcer(object):
    """
    Base class for decorating post-condition functions.

    When a service module is loading and functions with this decorator
    are parsed, the function will queue itself for injection into a
    client's after-call handler on demand.

    The name of the module that the function is in will be used to
    determine the service name of the event handler.

    The list of handlers is populated during the register call.
    """

    HANDLERS: Dict[EventName, "AfterEventHandler"] = dict()

    def __init__(self, post_condition_function: Callable) -> None:
        """
        When used as a decorator, this registers the function as an event
        handler.  The name of the module that the function is in will be
        used to determine the service name of the event handler, and the name
        of the function is the AWS API call to be enforced.
        """
        # len("boto3_post_conditions.services.") == 31
        service = post_condition_function.__module__[31:]
        event_name = f"after-call.{service}.{post_condition_function.__name__}"
        PostConditionEnforcer.HANDLERS[event_name] = post_condition_function

    @staticmethod
    def handle_event(
        event_handler: AfterEventHandler,
        call_args: Dict[str, Any],
        logger: Optional[Logger],
        timeout: TimeoutSpec,
    ) -> None:
        args = call_args["args"]
        kwargs = call_args["kwargs"]
        if kwargs["http_response"].status_code < 300:

            @retry(
                PostConditionNotSatisfiedError,
                tries=timeout.attempts,
                delay=timeout.delay,
                backoff=timeout.backoff,
                max_delay=timeout.max_delay,
                logger=logger,
            )
            def verify_post_condition(
                client: BaseClient,
                inner_event_handler: AfterEventHandler,
                *args,
                **kwargs,
            ):
                inner_event_handler(client, *args, **kwargs)

            # HACK!!!
            # the client and params are not passed down through handle_event, however
            # in order to initiate query calls to verify the modification that just
            # happened, we need these things; perhaps botocore would consider adding
            # this in the future to support this workflow
            client, api_params = PostConditionEnforcer._extract_client_and_params()
            kwargs["context"]["api_params"] = api_params

            verify_post_condition(client, event_handler, *args, **kwargs)

    @staticmethod
    def register(
        client: BaseClient,
        call: Optional[str] = None,
        logger: Optional[Logger] = None,
        timeout: Optional[TimeoutSpec] = None,
    ) -> None:
        """
        Given a boto3 client for a service, inject event handlers into the
        client that will enforce post-conditions for AWS API calls to that
        service.  This will dynamically load the correct post-conditions
        module on-demand.

        Arguments:
          client: a client obtained with boto3
          call: an optional call name to limit registration to
          logger: an optional logger to receive diagnostic messages
                  as well as any messages made by the retry library
          timeout: the post-condition wait strategy; one is provided
                   if not specified that has proven best for dealing
                   with each particular service.

        Raises:
          ImportError if there are no post-conditions for the client service
        """
        service_name = client.meta.service_model.service_name
        prefix = f"after-call.{service_name}."
        module = import_module(f".{service_name}", f"{__package__}.services")
        timeout = timeout or getattr(module, "DEFAULT_TIMEOUT", TimeoutSpec())

        for event_name, event_handler in PostConditionEnforcer.HANDLERS.items():
            if event_name.startswith(prefix):
                if (not call) or event_name.endswith(call):
                    if logger:
                        logger.debug(
                            f"registering {event_name} for post-condition enforcement with {event_handler}"
                        )
                    client.meta.events.register(
                        event_name,
                        # https://stackoverflow.com/questions/50298582/why-does-python-asyncio-loop-call-soon-overwrite-data
                        # if we do not pull these into the lambda this way they refer to the last for loop iteration
                        lambda *args, _event_handler=event_handler, _logger=logger, _timeout=timeout, **kwargs: PostConditionEnforcer.handle_event(  # noqa
                            _event_handler,
                            dict(args=args, kwargs=kwargs),
                            _logger,
                            _timeout,
                        ),
                    )

    @staticmethod
    def _extract_client_and_params() -> Tuple[BaseClient, Dict[str, Any]]:
        """
        Fish the client and api_params off the stack from _make_api_call in
        botocore.

        This is brittle, not pretty, and probably performs like crap, however
        botocore does not hand us the client or the api kwargs so we can do
        extra things, like validate post-conditions.  If botocore is changed
        to include these things in the context, we won't need to do this any
        more!
        """
        frame = inspect.currentframe()
        while frame:
            info = inspect.getframeinfo(frame)
            if info.function == "_make_api_call":
                return frame.f_locals["self"], frame.f_locals["api_params"]
            frame = frame.f_back
        raise NotImplementedError("something unexpected changed in botocore")
