# Custom View mutation schema conformance — evidence

Date: 2026-07-28. Workspace: Wortise (authorized write test by the repository
owner in-session). This fulfills the contract's condition in "Mapping de
Linear": automatic Shared View creation was gated on the necessary operations
being "disponibles y validadas en el schema GraphQL público para la cuenta
objetivo".

## Findings

1. `customViewCreate` exists in the public schema. `CustomViewCreateInput`
   accepts: client-side `id` (String), `name` (String!), `shared` (Boolean),
   `projectFilterData` (ProjectFilter), `filterData` (IssueFilter), plus
   description/icon/color/teamId/projectId/ownerId (unused by this extension).
2. The view's model is **inferred from which filter field is present**:
   `projectFilterData` → `modelName: Project`; `filterData` →
   `modelName: Issue`. There is no explicit model input.
3. Round-trip verified with two authorized test creations
   (`speckit-conformance-test / Features` and `… / Work`, deleted by the owner
   afterwards): client-side UUIDs honored verbatim, `shared: true` persists,
   and the canonical id-based filters
   (`{"labels": {"some": {"id": {"eq": <label>}}}}` /
   `{"project": {"labels": {"some": {"id": {"eq": <label>}}}}}`) are stored
   byte-identically — stronger than the name-based serialization the Linear UI
   produces for manually created views.

## Consequence

`seed` may create the two repository Shared Views through the allowlisted
mutation path (`custom_view.create` with client UUID, name, shared, canonical
id-based filter), eliminating the manual-creation step from onboarding.
`customViewUpdate`/`customViewDelete` remain forbidden, consistent with the
extension's no-update/no-delete policy for human-ownable resources.
