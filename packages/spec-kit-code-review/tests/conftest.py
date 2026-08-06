"""Test helpers live in tests.support for standard-library unittest discovery."""

# The consumer and adversarial fixtures contain files that look like tests on
# purpose (a consumer repository has tests; the hostile candidate has bait).
# They are fixture content, never this suite's own tests.
collect_ignore_glob = ["fixtures/*"]
