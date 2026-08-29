# Stage 4 acceptance — role bundles and the default preset

> Version numbers below predate the renumbering to the `0.x` line; the
> `bundles/v1.0.0` release they name no longer exists. The evidence is
> kept as recorded.

**Status: PERFORMED. Date: 2026-08-04.** `scripts/conformance/bundles.sh`
(exit 0, ~9 s, repeatable) proves in a fresh consumer per role, with the
real `catalog/*.json` served locally and the real artifacts:

- `bundle install <role>` installs exactly the role's set: product =
  default preset + linear; developer = + git + code-review; reviewer =
  default preset + code-review. Extensions outside the role are absent.
- The preset resolves all four workflow templates as `default v1.0.0`.
- `bundle remove` uninstalls only what the bundle contributed (a foreign
  extension survives), and the coexist phase proves the refcount: after
  installing developer + reviewer, removing reviewer leaves the shared
  code-review extension and preset in place.

Dogfooding: this repository dropped `.specify/templates/overrides/` and
dev-installs the preset (`specify preset resolve tasks-template` answers
`default v1.0.0`); no template is duplicated in git.

Pending publication (owner): push (catalogs go live on raw main) and the
`bundles/v1.0.0` release with the four artifacts plus checksums.

**Re-verified 2026-08-04 against the published catalogs and release.** In a
fresh consumer following `docs/guide.md` only: the three live catalogs
registered (extension and preset catalogs need explicit `--install-allowed`;
the guide now says so), and `specify bundle install developer` resolved the
`bundles/v1.0.0` artifact and installed its four components — git, linear
0.4.0, code-review 0.2.1, and the `default` preset resolving all templates.
