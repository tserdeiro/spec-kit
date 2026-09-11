# Upstream submission base

Target: `c173bf19a6654e3b05386ec3599349a55282b897`, the upstream `main`
revision captured for this review. This is not the distribution's installed pin.

Apply root patches 0001–0009 in numerical order, substituting this directory's
0004 for the pinned variant. 0003 applies unchanged to both bases. The 0004
rebase preserves upstream's unrelated template changes, removes its newer
obsolete Cline note implementation/tests, and updates its hook-error regression
to the native resolver contract.

See [verification](../verification.md) for full-suite results and remaining
limitations. No PR, commit, push or CLI upgrade has been performed.
