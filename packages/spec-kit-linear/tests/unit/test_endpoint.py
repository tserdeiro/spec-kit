"""Doc "Cliente GraphQL" > "Override de endpoint" (normative).

The override is destination-only, environment-only, http-only against
loopback, and loud in every invocation. Every one of those rules is
fail-closed, so each is asserted here in both its accepting and its refusing
direction.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from spec_kit_linear.cli import main
from spec_kit_linear.config import find_endpoint_keys, find_secret_keys, load_config
from spec_kit_linear.credentials import Credentials
from spec_kit_linear.endpoint import (
    DEFAULT_ENDPOINT,
    ENDPOINT_ENV,
    endpoint_report,
    resolve_endpoint,
    validate_endpoint,
)
from spec_kit_linear.errors import AppError
from spec_kit_linear.linear_client import LinearClient
from tests.support.fake_graphql import FakeGraphQLResponse, FakeGraphQLServer
from tests.support.fixtures import copy_consumer_fixture, isolate_operator_global_env


# A loopback destination with nothing listening on it. Used only as a *value*
# in these tests: no test here opens a socket.
UNREACHABLE_ENDPOINT = "http://127.0.0.1:9/graphql"


class EndpointValidationTests(unittest.TestCase):
    def test_unset_environment_resolves_to_production(self) -> None:
        self.assertEqual(resolve_endpoint({}), DEFAULT_ENDPOINT)

    def test_https_is_accepted_against_any_host(self) -> None:
        for value in (
            DEFAULT_ENDPOINT,
            "https://linear.internal.example/graphql",
            "https://api.linear.app:8443/graphql",
            "https://127.0.0.1:8443/graphql",
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_endpoint(value), value)
                self.assertEqual(resolve_endpoint({ENDPOINT_ENV: value}), value)

    def test_plain_http_is_accepted_only_against_loopback(self) -> None:
        for value in (
            "http://127.0.0.1:8123/graphql",
            "http://localhost:8123/graphql",
            "http://[::1]:8123/graphql",
            "http://localhost/graphql",
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_endpoint(value), value)

    def test_plain_http_against_any_other_host_is_configuration_error(self) -> None:
        for value in (
            "http://api.linear.app/graphql",
            "http://linear.internal.example/graphql",
            "http://10.0.0.5:8123/graphql",
            "http://127.0.0.2:8123/graphql",
            "http://localhost.evil.example/graphql",
        ):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as raised:
                    validate_endpoint(value)
                self.assertEqual(raised.exception.code, 3)
                self.assertEqual(raised.exception.category, "configuration")
                self.assertEqual(raised.exception.diagnostics[0].code, "linear_endpoint")

    def test_unsupported_scheme_is_configuration_error(self) -> None:
        for value in ("ftp://api.linear.app/graphql", "file:///tmp/graphql", "ws://localhost:8123/graphql", "//localhost/graphql"):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as raised:
                    validate_endpoint(value)
                self.assertEqual(raised.exception.code, 3)

    def test_empty_or_non_url_values_are_configuration_errors(self) -> None:
        for value in ("", "   ", "api.linear.app/graphql", "localhost:8123", "https://", "not a url", None, 8123):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as raised:
                    validate_endpoint(value)
                self.assertEqual(raised.exception.code, 3)

    def test_an_empty_override_never_silently_falls_back_to_production(self) -> None:
        """Set-but-empty is an error, not "use production": somebody who
        deliberately redirected the destination must not be quietly
        reconnected to their real workspace by a typo."""

        with self.assertRaises(AppError) as raised:
            resolve_endpoint({ENDPOINT_ENV: ""})
        self.assertEqual(raised.exception.code, 3)

    def test_embedded_credentials_query_and_fragment_are_rejected(self) -> None:
        for value in (
            "https://user:secret@api.linear.app/graphql",
            "https://api.linear.app/graphql?api_key=secret",
            "https://api.linear.app/graphql#fragment",
        ):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as raised:
                    validate_endpoint(value)
                self.assertEqual(raised.exception.code, 3)

    def test_no_interpolation_or_expansion_is_ever_performed(self) -> None:
        """An unexpanded shell variable or a smuggled second value must fail,
        never be expanded and never be split."""

        for value in (
            "http://localhost:$PORT/graphql",
            "https://api.linear.app/graphql https://evil.example/graphql",
            "https://api.linear.app/graphql\nhttps://evil.example/graphql",
            "$SPECKIT_LINEAR_GRAPHQL_ENDPOINT",
        ):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as raised:
                    validate_endpoint(value)
                self.assertEqual(raised.exception.code, 3)

    def test_out_of_range_port_is_rejected(self) -> None:
        for value in ("http://127.0.0.1:99999/graphql", "http://127.0.0.1:0/graphql"):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as raised:
                    validate_endpoint(value)
                self.assertEqual(raised.exception.code, 3)

    def test_surrounding_whitespace_is_rejected_rather_than_trimmed(self) -> None:
        """The value is used verbatim. Trimming would mean the endpoint that
        gets used is not the string that was configured."""

        for value in (" https://api.linear.app/graphql", "https://api.linear.app/graphql ", "\thttps://api.linear.app/graphql\n"):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as raised:
                    validate_endpoint(value)
                self.assertEqual(raised.exception.code, 3)

    def test_documented_loopback_false_negatives_fail_closed(self) -> None:
        """Spellings that are loopback in fact but are not the three names the
        contract lists. Each is a clear error with an https way out, never a
        silent acceptance -- the strictness is the point."""

        for value in ("http://[0:0:0:0:0:0:0:1]/graphql", "http://[::ffff:127.0.0.1]/graphql", "http://127.0.0.2/graphql"):
            with self.subTest(value=value):
                with self.assertRaises(AppError) as raised:
                    validate_endpoint(value)
                self.assertEqual(raised.exception.code, 3)

    def test_the_client_shares_the_single_validator(self) -> None:
        """Validation lives in one place: handing the client a bad endpoint
        programmatically fails with the same exit code as a bad override."""

        credentials = type("_Credentials", (), {"headers": staticmethod(lambda: {})})()
        with self.assertRaises(AppError) as raised:
            LinearClient(credentials, endpoint="http://api.linear.app/graphql")
        self.assertEqual(raised.exception.code, 3)

    def test_report_distinguishes_production_from_an_override(self) -> None:
        default = endpoint_report(DEFAULT_ENDPOINT)
        self.assertTrue(default["is_default"])
        self.assertTrue(default["is_production"])
        self.assertFalse(default["override_active"])

        overridden = endpoint_report(UNREACHABLE_ENDPOINT)
        self.assertFalse(overridden["is_production"])
        self.assertTrue(overridden["override_active"])
        self.assertEqual(overridden["source"], ENDPOINT_ENV)
        self.assertEqual(overridden["url"], UNREACHABLE_ENDPOINT)


class EndpointRedirectRefusalTests(unittest.TestCase):
    """The override fixes the destination of the whole exchange, not just of
    the first request.

    `urlopen`'s default redirect handler rebuilds a 3xx against `Location`
    while copying `Authorization`, and never re-validates the host: following
    one would send the real Linear key to a destination the validator never
    saw, defeating the single-place resolution entirely.
    """

    def test_a_redirect_is_refused_and_the_credential_never_leaves(self) -> None:
        try:
            with FakeGraphQLServer(
                responses=[
                    FakeGraphQLResponse(
                        {"data": {}},
                        status=302,
                        headers={"Location": "https://api.linear.app/graphql"},
                    )
                ]
            ) as server:
                client = LinearClient(Credentials("api_key", "super-secret-key"), endpoint=server.endpoint, max_attempts=1)
                with self.assertRaises(AppError) as raised:
                    client.query("query Viewer { viewer { id } }")
        except PermissionError:
            self.skipTest("the execution sandbox forbids loopback socket binding")

        self.assertEqual(raised.exception.code, 9)
        self.assertFalse(raised.exception.retryable)
        self.assertIn("linear_redirect", [diagnostic.code for diagnostic in raised.exception.diagnostics])
        # Exactly one request was made: the redirect was never followed, so
        # the Authorization header never travelled to the redirect target.
        self.assertEqual(len(server.requests), 1)

    def test_the_default_opener_does_not_carry_a_redirect_handler(self) -> None:
        """A structural guard: the redirect refusal must not be reintroduced
        by someone restoring `urlopen` as the default transport."""

        from spec_kit_linear import linear_client as client_module

        signature = inspect.signature(LinearClient.__init__)
        self.assertIs(signature.parameters["opener"].default, client_module._open_without_redirects)
        handlers = [type(handler).__name__ for handler in client_module._OPENER.handlers]
        self.assertIn("_RefuseRedirects", handlers)
        self.assertNotIn("HTTPRedirectHandler", handlers)


class EndpointConfigurationRejectionTests(unittest.TestCase):
    """Neither the committed shared config nor the local one may set it."""

    def setUp(self) -> None:
        temporary, root = copy_consumer_fixture()
        self.addCleanup(temporary.cleanup)
        self.root = root
        self.shared = root / "speckit-linear.yml"

    def _with_shared_key(self, line: str, *, inside_linear: bool) -> None:
        """Write the shared config with one extra key, without duplicating a
        top-level section (which the loader would reject as malformed YAML
        before it ever got to the endpoint rule)."""

        original = self.shared.read_text(encoding="utf-8")
        self.addCleanup(self.shared.write_text, original, "utf-8")
        if inside_linear:
            updated = original.replace('  team_key: "WOR"', f'  team_key: "WOR"\n  {line}', 1)
            self.assertNotEqual(updated, original)
        else:
            updated = f"{original}\n{line}\n"
        self.shared.write_text(updated, encoding="utf-8")

    def test_unmodified_fixture_still_loads(self) -> None:
        config, _shared = load_config(self.root)
        self.assertEqual(config["repository"]["slug"], "sample-repository")

    def test_a_repository_git_remote_url_is_not_a_graphql_destination(self) -> None:
        """`repository.url` is the consumer's Git remote: the rejection must
        not swallow it."""

        self.assertEqual(find_endpoint_keys({"repository": {"url": "https://github.com/example/x"}}), [])

    def test_endpoint_key_in_the_shared_config_is_exit_code_three(self) -> None:
        cases = (
            ('endpoint: "http://127.0.0.1:9/graphql"', True),
            ('graphql_endpoint: "http://127.0.0.1:9/graphql"', True),
            ('graphql-endpoint: "http://127.0.0.1:9/graphql"', True),
            ('GraphQL_Endpoint: "http://127.0.0.1:9/graphql"', True),
            ('api_url: "http://127.0.0.1:9/graphql"', True),
            ('url: "http://127.0.0.1:9/graphql"', True),
            ('host: "127.0.0.1"', True),
            ('endpoint: "http://127.0.0.1:9/graphql"', False),
            ('graphql_url: "http://127.0.0.1:9/graphql"', False),
            ('SPECKIT_LINEAR_GRAPHQL_ENDPOINT: "http://127.0.0.1:9/graphql"', False),
        )
        for line, inside_linear in cases:
            with self.subTest(line=line, inside_linear=inside_linear):
                original = self.shared.read_text(encoding="utf-8")
                self._with_shared_key(line, inside_linear=inside_linear)
                try:
                    with self.assertRaises(AppError) as raised:
                        load_config(self.root)
                finally:
                    self.shared.write_text(original, encoding="utf-8")
                self.assertEqual(raised.exception.code, 3)
                self.assertEqual(raised.exception.category, "configuration")
                self.assertEqual(raised.exception.diagnostics[0].code, "config_endpoint")
                self.assertEqual(raised.exception.diagnostics[0].path, str(self.shared.resolve()))

    def test_rejection_is_an_error_never_a_warning(self) -> None:
        self._with_shared_key('endpoint: "http://127.0.0.1:9/graphql"', inside_linear=True)
        with self.assertRaises(AppError) as raised:
            load_config(self.root)
        self.assertEqual([diagnostic.severity for diagnostic in raised.exception.diagnostics], ["error"])

    def test_scan_ignores_operator_chosen_team_member_aliases(self) -> None:
        self.assertEqual(find_endpoint_keys({"team": {"members": {"endpoint": "a@example.com"}}}), [])
        self.assertEqual(find_endpoint_keys({"repository": {"url": "https://github.com/example/x"}}), [])
        self.assertEqual(find_endpoint_keys({"linear": {"endpoint": "x"}}), ["linear.endpoint"])

    def test_scan_walks_sequences(self) -> None:
        """A mapping written inside a list is still a mapping somebody wrote;
        a scan that only descends through mappings would miss it."""

        self.assertEqual(find_endpoint_keys({"linear": [{"endpoint": "x"}]}), ["linear[0].endpoint"])
        self.assertEqual(find_endpoint_keys({"linear": [{"url": "x"}]}), ["linear[0].url"])
        self.assertEqual(find_endpoint_keys([{"graphql_endpoint": "x"}]), ["[0].graphql_endpoint"])
        self.assertEqual(find_endpoint_keys({"team": {"members": [{"endpoint": "a@example.com"}]}}), [])

    def test_secret_scan_walks_sequences_too(self) -> None:
        self.assertEqual(find_secret_keys({"linear": [{"api_key": "x"}]}), ["linear[0].api_key"])

    def test_plausible_redirection_spellings_are_all_rejected(self) -> None:
        for mapping, expected in (
            ({"linear": {"workspace_url": "x"}}, ["linear.workspace_url"]),
            ({"linear": {"instance_url": "x"}}, ["linear.instance_url"]),
            ({"linear": {"self_hosted_url": "x"}}, ["linear.self_hosted_url"]),
            ({"linear": {"graphql_server": "x"}}, ["linear.graphql_server"]),
            ({"linear": {"api_root": "x"}}, ["linear.api_root"]),
            ({"linear": {"domain": "x"}}, ["linear.domain"]),
            ({"linear": {"address": "x"}}, ["linear.address"]),
            ({"linear": {"base": "x"}}, ["linear.base"]),
            # Tier 2 outside its scopes stays legal: repository.url is the
            # consumer's Git remote and predates all of this.
            ({"repository": {"url": "x", "host": "y"}}, []),
        ):
            with self.subTest(mapping=mapping):
                self.assertEqual(find_endpoint_keys(mapping), expected)


class _UnreachableClient:
    """Every remote call fails the way an unreachable endpoint fails."""

    def __getattr__(self, name: str):
        def _fail(*args: object, **kwargs: object):
            raise AppError(
                "Linear read request could not reach the service",
                code=8,
                category="transport",
                retryable=True,
            )

        return _fail


class EndpointNoticeTests(unittest.TestCase):
    """A non-production endpoint is announced in every invocation of doctor,
    status, push and seed -- in the human render and in its own JSON field --
    and no flag can silence it."""

    def setUp(self) -> None:
        isolate_operator_global_env(self)
        temporary, root = copy_consumer_fixture()
        self.addCleanup(temporary.cleanup)
        self.root = root
        # `doctor` requires a Git worktree; without one every invocation here
        # would fail on a prerequisite before reaching what is being asserted.
        subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)

    def _invoke(self, arguments: list[str], *, endpoint: str | None = UNREACHABLE_ENDPOINT) -> tuple[int, str, str]:
        environment = {"LINEAR_API_KEY": "test-key"}
        if endpoint is not None:
            environment[ENDPOINT_ENV] = endpoint
        out, err = StringIO(), StringIO()
        with patch.dict(os.environ, environment, clear=False):
            if endpoint is None:
                os.environ.pop(ENDPOINT_ENV, None)
            # `LinearClient` is patched rather than `cli._linear_client`, so
            # that the real construction site still runs: announcing on client
            # construction is the mechanism under test, and patching it away
            # would test the mock instead.
            with patch("spec_kit_linear.cli.LinearClient", return_value=_UnreachableClient()):
                with redirect_stdout(out), redirect_stderr(err):
                    code = main(arguments)
        return code, out.getvalue(), err.getvalue()

    def _surfaces(self) -> dict[str, list[str]]:
        """The surfaces that always announce, whether or not they build a
        client -- `doctor --offline` never does."""

        return {
            "doctor": ["doctor", "--offline", "--root", str(self.root)],
            "status": ["status", "--root", str(self.root), "--feature", "001"],
            "push": ["push", "--root", str(self.root), "--feature", "001", "--dry-run"],
            "push-hook": ["push", "--hook", "--root", str(self.root), "--feature", "001"],
        }

    def _client_building_surfaces(self) -> dict[str, list[str]]:
        """Every other command that reaches a Linear endpoint. A rule written
        as a list of command names would leave these silent."""

        return {
            "onboard": ["onboard", "--root", str(self.root), "--team-key", "WOR", "--repository", "spec-kit", "--dry-run"],
        }

    def test_every_surface_announces_a_non_production_endpoint_in_the_human_render(self) -> None:
        for command, arguments in self._surfaces().items():
            with self.subTest(command=command):
                _code, _out, err = self._invoke(arguments)
                self.assertIn("NOT LINEAR PRODUCTION", err)
                self.assertIn(UNREACHABLE_ENDPOINT, err)
                self.assertIn(ENDPOINT_ENV, err)

    def test_every_surface_reports_the_endpoint_in_its_own_json_field(self) -> None:
        for command, arguments in self._surfaces().items():
            with self.subTest(command=command):
                _code, out, _err = self._invoke([*arguments, "--json"])
                payload = json.loads(out)
                self.assertIn("endpoint", payload)
                self.assertEqual(payload["endpoint"]["url"], UNREACHABLE_ENDPOINT)
                self.assertTrue(payload["endpoint"]["override_active"])
                self.assertFalse(payload["endpoint"]["is_production"])

    def test_every_command_that_builds_a_client_announces_too(self) -> None:
        """Doc "Override de endpoint" as amended: the rule is every surface
        that can reach a Linear endpoint, not a list of four command names."""

        for command, arguments in self._client_building_surfaces().items():
            with self.subTest(command=command):
                _code, out, err = self._invoke([*arguments, "--json"])
                self.assertIn("NOT LINEAR PRODUCTION", err, f"{command} reached a Linear endpoint silently")
                payload = json.loads(out)
                self.assertEqual(payload["endpoint"]["url"], UNREACHABLE_ENDPOINT)

    def test_quiet_does_not_suppress_the_notice(self) -> None:
        for command, arguments in self._surfaces().items():
            with self.subTest(command=command):
                _code, out, err = self._invoke([*arguments, "--quiet"])
                self.assertEqual(out, "")
                self.assertIn("NOT LINEAR PRODUCTION", err)

    def test_json_mode_does_not_suppress_the_notice_and_keeps_stdout_parseable(self) -> None:
        _code, out, err = self._invoke(["doctor", "--offline", "--root", str(self.root), "--json"])
        self.assertIn("NOT LINEAR PRODUCTION", err)
        json.loads(out)

    def test_json_and_quiet_together_do_not_suppress_the_notice(self) -> None:
        """Each flag alone keeps the notice; combining them must not be a way
        to lose it."""

        for command, arguments in self._surfaces().items():
            with self.subTest(command=command):
                _code, out, err = self._invoke([*arguments, "--json", "--quiet"])
                self.assertIn("NOT LINEAR PRODUCTION", err)
                self.assertEqual(json.loads(out)["endpoint"]["url"], UNREACHABLE_ENDPOINT)

    def test_quiet_never_swallows_an_invalid_configuration(self) -> None:
        """The managed Git-hook dispatchers always pass `--quiet`; a
        fail-closed refusal nobody can see is indistinguishable from
        success."""

        code, out, err = self._invoke(
            ["push", "--hook", "--root", str(self.root), "--feature", "001", "--quiet"],
            endpoint="http://linear.internal.example/graphql",
        )
        self.assertEqual(code, 3)
        self.assertEqual(out, "")
        self.assertIn("linear_endpoint", err)

    def test_the_real_client_is_constructed_against_the_override(self) -> None:
        """Nothing above proves the client itself is pointed at the override,
        because every one of those tests replaces it. This one does not."""

        from spec_kit_linear import cli as cli_module

        with patch.dict(os.environ, {ENDPOINT_ENV: UNREACHABLE_ENDPOINT, "LINEAR_API_KEY": "test-key"}, clear=False):
            err = StringIO()
            with redirect_stderr(err):
                client = cli_module._linear_client()
        self.assertEqual(client.endpoint, UNREACHABLE_ENDPOINT)
        self.assertIn("NOT LINEAR PRODUCTION", err.getvalue())

        with patch.dict(os.environ, {"LINEAR_API_KEY": "test-key"}, clear=False):
            os.environ.pop(ENDPOINT_ENV, None)
            err = StringIO()
            with redirect_stderr(err):
                client = cli_module._linear_client()
        self.assertEqual(client.endpoint, DEFAULT_ENDPOINT)
        self.assertEqual(err.getvalue(), "")

    def test_a_failing_invocation_still_announces_the_endpoint(self) -> None:
        """The notice is emitted before the command runs, so an invocation
        that then fails closed still carries it -- in both surfaces."""

        code, out, err = self._invoke(["status", "--root", str(self.root), "--feature", "001", "--json"])
        self.assertEqual(code, 8)
        self.assertIn("NOT LINEAR PRODUCTION", err)
        self.assertEqual(json.loads(out)["endpoint"]["url"], UNREACHABLE_ENDPOINT)

    def test_production_is_silent_and_keeps_the_published_result_shape(self) -> None:
        code, out, err = self._invoke(["doctor", "--offline", "--root", str(self.root), "--json"], endpoint=None)
        self.assertEqual(code, 0)
        self.assertNotIn("NOT LINEAR PRODUCTION", err)
        self.assertNotIn("endpoint", json.loads(out))

    def test_an_invalid_override_is_exit_code_three_for_every_command(self) -> None:
        for command, arguments in self._surfaces().items():
            with self.subTest(command=command):
                code, out, _err = self._invoke([*arguments, "--json"], endpoint="http://linear.internal.example/graphql")
                self.assertEqual(code, 3)
                payload = json.loads(out)
                self.assertEqual(payload["category"], "configuration")
                self.assertEqual(payload["diagnostics"][0]["code"], "linear_endpoint")


if __name__ == "__main__":  # pragma: no cover - parity with the other suites
    unittest.main()
