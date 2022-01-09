# boto3-post-conditions

 ![ci](https://github.com/jeking3/boto3_post_conditions/actions/workflows/test.yml/badge.svg)
[![codecov](https://codecov.io/gh/jeking3/boto3-post-conditions/branch/main/graph/badge.svg?token=NP7WihxzHD)](https://codecov.io/gh/jeking3/boto3-post-conditions)
[![open issues](https://img.shields.io/github/issues-raw/jeking3/boto3_post_conditions)](https://github.com/jeking3/boto3_post_conditions/issues)
[![license](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Most AWS APIs are eventually consistent with few guarantees.  For example when
you use SSM `put_parameter` (which succeeds), then immediately call `get_parameter`,
you might get an error such as `ParameterNotFound`.  Welcome to the world of
eventual consistency.  Anyone who has worked with the AWS CLI or API has been
forced to do one of two things:

1. Add sleep logic to wait for things to align, or
2. Add retry logic to wait for things to align.

This library injects logic for post-condition blocking checks in boto3
to eliminate the majority of retry code that everyone has been forced to
add (and develop tests for) in their own code.  This is especially useful
in serial scripts that manipulate AWS, where different commands in the script
depend on changes from the previous command to be fully realized.  Hopefully
this sort of logic can make its way into botocore in the future so that
serialized scripts can take advantage of it and become vastly simplified.

## Quick Start

### Compatibility

boto3-post-conditions supports at least some of the following AWS subsystems:

- SSM Parameter Store
- Secrets Manager

### Installing

    pip install boto3-post-conditions

or

    poetry add boto3-post-conditions

### Using

Create a boto3 client like you normally would.  To enforce post-conditions
on calls to that client, register the client with the `PostConditionEnforcer`:

    import boto3
    from boto3_post_conditions import PostConditionEnforcer

    client = boto3.client("ssm")
    PostConditionEnforcer.register(client)

The enforcer will inject event handlers into the client definition to
block returning from your API calls until changes are actually realized
in the AWS service you are modifying.

## Limitations

It's beta, so there are going to be some major gaps...

- Only supports some of Secrets Manager and SSM initially.
- Post-conditions are always checked serially after each modification.
  There is no batch post-condition processing yet, but certainly
  being able to wrap boto calls in a context manager and then finalize
  their changes all at once (allowing AWS to process all the requests
  in parallel) is going to be useful.

## Background

Every developer who has worked with the AWS API has encountered eventual
consistency issues.  This behavior has led virtually every reliable product
that leverages the AWS API to add their own code to defeat the effects of
eventual consistency.  The best way to deal with eventual consistency in a
pipeline is to add post-condition checks.  For example, if you delete a secret
in AWS Secrets Manager, it is not immediately deleted.  It is scheduled for
deletion and then it is eventually deleted.  If you attempt to insert a new
secret with the same name during this transition you get an error.  You may
even still be able to read the secret even though the delete call returned
success.

AWS documents [eventual consistency](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/query-api-troubleshooting.html#eventual-consistency)
separately for each of their subsystems.

Tag management falls into the same category, as some AWS subsystems rely on
the Resource and Tag Manager to handle tagging, and that means more eventual
consistency.  If you modify or remove a tag on a resource, it is often not
realized immediately (causing a situation where you cannot read what you
wrote), so follow-up code that depends on that tag being modified or deleted
can fail.

boto3-post-conditions hooks into [botocore](https://github.com/boto/botocore)
in a manner similar to the simulation library [moto](https://github.com/spulec/moto)
such that when a call completes that modifies something, the client verifies
that the change has been realized.  This does require a little bit of stack
inspection, as the client and original call parameters are not passed through
the handle_event mechanism.

## Theory of Operation

Each boto3 call that makes a modification can be verified for liveness with
a subsequent read call.  The "after-call" boto3 event occurs after every call
allowing code to plug into the request stream.  When the response indicates
a change is successful, post-conditions can be enforced by reading back the
resource and ensuring the expected change is there.

Take the Systems Manager (SSM) Parameter Store, for example.  As an eventually
consistent system, extra care must be taken to avoid some common pitfalls,
such as:

- Calling put_parameter immediately followed by get_parameter has no guarantee
  of success.  In fact, it can raise a ParameterNotFound.
- Calling delete_parameter immediately followed by get_parameter can still return
  the parameter.

boto3_post_conditions adds logic to ensure that the modifications you are making
are realized by that subsystem's control plane before returning control to the
caller.  For example with put_parameter, boto3_post_conditions will ensure that:

- The parameter can be read (with GetParameter) to handle the case of a novel
  parameter being added.
- The parameter's tags can be read, should the Tags be set during creation.
  The resource and tag manager is a separate subsystem which adds even more
  delays to realization.

Every modification or deletion has a post-condition remedy that can ensure
the vast majority of these cases are eliminated, and virtually removing retry
logic from your code and tests!  As proof, look at the recorded test for
`test_ssm_integration`.

## Development

This project uses [poetry](https://pypi.org/project/poetry/) to manage the development
virtual environment.  To get started you need to install poetry using pip, then run
the command `poetry install`.  The project is configured to store the virtual environment
in the `.venv` directory.

To update supported services, look in the `boto3_post_conditions/services` directory.
There is one module for each service.  Each API call for a service that has post-conditions
has an identically named function with a decorator.  This package also extends the event
data carried through such that the original call parameters and client are available.

Never call the original API from the post-condition function (unless you like infinite
recursion)!

Each post-condition method should guarantee visibility of the API that was called. For
example when something is deleted, the function should attempt to get that resource
and raise a `PostConditionNotSatisfiedError` if it is still there.  The framework will
then enter a retry loop, calling the function again after an increasing delay.

Unit testing is required for new code.  If you submit a PR without testing it will not be
approved.
