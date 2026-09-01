"""The one place where the GraphQL endpoint is resolved, validated and announced.

Doc "Cliente GraphQL" > "Override de endpoint" (normative). Without an
override every invocation reaches the operator's *production* Linear
workspace by construction, with whatever credentials the environment
supplies. ``SPECKIT_LINEAR_GRAPHQL_ENDPOINT`` exists so a test, a
conformance script or a cautious evaluator can point the client somewhere
else -- and every rule around it is fail-closed:

* it overrides the **destination, never the credential** (the API key keeps
  coming from the environment under the usual rules);
* it is an **environment value and nothing else**: neither the committed
  shared configuration nor the local one may carry an endpoint key (see
  :func:`spec_kit_linear.config.find_endpoint_keys`), because a per-repository
  committed file able to redirect a whole team's reads and writes is a
  redirection vector wearing the costume of an innocuous config change;
* the value must be an **absolute http/https URL**, with plain ``http``
  accepted only against loopback; anything else is exit code 3;
* no interpolation and no expansion -- the string is used verbatim;
* an endpoint that is not production is **loud in every invocation** and
  cannot be silenced by any flag (see :func:`endpoint_banner`).

Resolution and validation live here, and only here, so that the CLI, the
client and the tests cannot drift into three subtly different notions of
"which endpoint am I talking to".
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from .errors import AppError, Diagnostic


DEFAULT_ENDPOINT = "https://api.linear.app/graphql"
ENDPOINT_ENV = "SPECKIT_LINEAR_GRAPHQL_ENDPOINT"

# Plain http is accepted only against these three exact hostnames, which are
# the three the contract names. `localhost` is included because a loopback
# test server is routinely reached by name; every other host must use https,
# no matter how private it looks.
#
# The comparison is deliberately exact, which accepts a set of false
# *negatives* -- spellings that are loopback in fact but rejected here:
# `http://[0:0:0:0:0:0:0:1]/` (the expanded form of ::1),
# `http://[::ffff:127.0.0.1]/` (IPv4-mapped), `http://127.0.0.2/` (all of
# 127.0.0.0/8 is loopback, only .1 is listed), and `http://localhost:0/`
# (port 0 is refused by the port check, not by this set). Every one of those
# fails closed with a clear message, and https always works, so the cost of
# the strictness is a one-line fix by the operator rather than a hole. An
# inexact matcher -- a prefix test, a `127.` startswith, an "is it private"
# heuristic -- is how `localhost.evil.example` gets accepted.
#
# Conceptually `localhost` is the weakest member: it is a *name*, and a
# hostile or merely wrong /etc/hosts can point it off the loopback interface.
# It stays because refusing it would break the ordinary local-server workflow
# this override exists for, and because an attacker able to edit /etc/hosts
# has already won more directly. `127.0.0.1` and `::1` have no such caveat.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Doc "Override de endpoint": the surfaces the contract names explicitly,
# which must report a non-production endpoint in every invocation whether or
# not they end up building a Linear client.
#
# This is a *floor*, not the whole rule. Any invocation that constructs a
# Linear client announces too, whatever its command is -- see
# `cli._linear_client`, which is the single construction site. Keeping the
# named four unconditional matters for exactly one case: `doctor --offline`
# deliberately builds no client, yet it is the diagnostic command, and
# "where would this have gone?" is the question it exists to answer. It is
# also what makes a hermetic conformance gate possible without contacting
# anything.
ALWAYS_ANNOUNCE_COMMANDS = frozenset({"doctor", "onboard", "push", "status"})

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _reject(message: str, detail: str) -> AppError:
    return AppError(
        message,
        code=3,
        category="configuration",
        diagnostics=[Diagnostic("linear_endpoint", detail)],
    )


def validate_endpoint(value: object, *, origin: str = ENDPOINT_ENV) -> str:
    """Return ``value`` as a usable endpoint, or raise exit code 3.

    Accepts an absolute ``https`` URL against any host, and an absolute
    ``http`` URL only against :data:`LOOPBACK_HOSTS`. Rejects an empty value,
    a non-string, anything that is not an absolute URL, embedded credentials,
    query strings and fragments, an unparseable port, and any whitespace or
    control character *anywhere* in the value, surrounding it included
    (which is also how a would-be ``$VAR`` shell expansion or a smuggled
    second URL fails: the value is never interpolated, never expanded, never
    split, and never trimmed -- what is configured is what is used).
    """

    if not isinstance(value, str):
        raise _reject(
            "the Linear GraphQL endpoint override must be a string",
            f"{origin} must be an absolute http(s) URL",
        )
    candidate = value
    if not candidate:
        raise _reject(
            "the Linear GraphQL endpoint override is empty",
            f"{origin} is set but empty; unset it to use {DEFAULT_ENDPOINT}, or set an absolute http(s) URL",
        )
    if any(character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F for character in candidate):
        raise _reject(
            "the Linear GraphQL endpoint override contains whitespace or control characters",
            f"{origin} must be a single absolute http(s) URL with no surrounding or embedded whitespace, used verbatim without interpolation or expansion",
        )
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as error:
        raise _reject(
            "the Linear GraphQL endpoint override is not a valid URL",
            f"{origin} must be an absolute http(s) URL: {error}",
        ) from error
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise _reject(
            "the Linear GraphQL endpoint override must use http or https",
            f"{origin} must be an absolute http(s) URL; got scheme '{parsed.scheme or '(none)'}'",
        )
    if not parsed.hostname:
        raise _reject(
            "the Linear GraphQL endpoint override has no host",
            f"{origin} must be an absolute http(s) URL including a host",
        )
    if parsed.username or parsed.password:
        raise _reject(
            "the Linear GraphQL endpoint override must not embed credentials",
            f"{origin} must not contain a username or password; the API key comes only from the environment",
        )
    if parsed.query or parsed.fragment:
        raise _reject(
            "the Linear GraphQL endpoint override must not carry query data",
            f"{origin} must not contain a query string or fragment",
        )
    if port is not None and not 1 <= port <= 65535:
        raise _reject(
            "the Linear GraphQL endpoint override has an invalid port",
            f"{origin} port must be between 1 and 65535",
        )
    # `urlsplit(...).hostname` is already lowercased and already has the IPv6
    # brackets removed, so `http://[::1]/` arrives here as the bare `::1`.
    if parsed.scheme == "http" and parsed.hostname not in LOOPBACK_HOSTS:
        raise _reject(
            "an insecure http Linear GraphQL endpoint is allowed only against loopback",
            f"{origin} may use plain http only for {', '.join(sorted(LOOPBACK_HOSTS))}; every other host requires https",
        )
    return candidate


def resolve_endpoint(environment: Mapping[str, str] | None = None) -> str:
    """Resolve the effective endpoint from the process environment.

    Unset means production. Set means validated: a bad override is exit code
    3, never a silent fallback to production -- somebody who deliberately
    redirected the destination must not be quietly reconnected to their real
    workspace by a typo.
    """

    values = os.environ if environment is None else environment
    if ENDPOINT_ENV not in values:
        return DEFAULT_ENDPOINT
    return validate_endpoint(values[ENDPOINT_ENV], origin=ENDPOINT_ENV)


def is_default_endpoint(endpoint: str) -> bool:
    """True when ``endpoint`` is the production Linear API."""

    return endpoint == DEFAULT_ENDPOINT


def endpoint_report(endpoint: str) -> dict[str, object]:
    """The JSON field describing the effective endpoint.

    Its own top-level ``endpoint`` object, not a diagnostic among others: a
    machine consumer must be able to tell, without parsing prose, that a
    result did not come from the production workspace.
    """

    overridden = not is_default_endpoint(endpoint)
    report: dict[str, object] = {
        "url": endpoint,
        "source": ENDPOINT_ENV if overridden else "default",
        "is_default": not overridden,
        "override_active": overridden,
        "is_production": not overridden,
    }
    if overridden:
        report["notice"] = (
            "this invocation did NOT talk to the Linear production workspace; "
            f"{ENDPOINT_ENV} redirected it to {endpoint}"
        )
    return report


def endpoint_banner(endpoint: str) -> str:
    """The unsilenceable human notice for a non-production endpoint.

    Written to stderr on every announcing invocation, in every output mode.
    It is deliberately immune to ``--quiet`` and to ``--json``, together or
    separately: a person must never be able to believe they synchronized
    their workspace when they in fact spoke to a local server, and repeated
    noise is cheaper than one silence at the wrong moment.

    Stderr is the choice that makes that true. ``--json`` owns stdout and
    ``--quiet`` suppresses the stdout render, so a notice on stdout would be
    invisible in both and would corrupt the JSON in the first.

    """

    rule = "!" * 72
    return (
        f"{rule}\n"
        f"! NOT LINEAR PRODUCTION -- this invocation talks to an overridden endpoint.\n"
        f"! endpoint: {endpoint}\n"
        f"! source:   {ENDPOINT_ENV} (environment override)\n"
        f"! Nothing reported below reflects the state of your Linear workspace.\n"
        f"{rule}\n"
    )
