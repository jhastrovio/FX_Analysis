# Maintenance Guide

This repo should stay lightweight, readable, and clearly inside the analytics-consumer boundary.

## Review Checklist

When reviewing doc or code changes, confirm:

1. FX_Analysis remains read-only with respect to `/FX_Data - General`.
2. Datasets are referenced through the manifest rather than hard-coded estate paths.
3. Outputs stay local, temporary, and non-authoritative.
4. New data needs are routed upstream through the data request path.
5. The docs still make the repo’s role obvious to a new contributor.
6. Descriptions of the Systemacro Research System, the Systemacro Website, and the OneDrive Data Store remain consistent with [07-systemacro-data-architecture.md](/Users/jameshassett/dev/FX_Analysis/docs/07-systemacro-data-architecture.md).

## Keeping The Boundaries Intact

- Analysis logic belongs in this repo.
- Authoritative data production does not.
- Temporary exports are fine.
- Permanent datasets are not.

If a proposed change blurs those lines, stop and check [03-read-only-contract.md](/Users/jameshassett/dev/FX_Analysis/docs/03-read-only-contract.md), [04-data-request-contract.md](/Users/jameshassett/dev/FX_Analysis/docs/04-data-request-contract.md), and [05-extension-guidelines.md](/Users/jameshassett/dev/FX_Analysis/docs/05-extension-guidelines.md).

## Maintaining The Doc Set

- Keep [00-overview.md](/Users/jameshassett/dev/FX_Analysis/docs/00-overview.md) short and stable.
- Put operating-model changes in the top-level docs before adding new detail elsewhere.
- Use the decision docs as background rationale, not as the main onboarding path.
- Keep examples concrete and practical.

## Change Hygiene

- Prefer small reversible edits.
- Remove repeated explanations when one doc can say it clearly once.
- Add cross-links when a workflow depends on a contract or template.
- Document new metrics, dashboards, or scripts close to where contributors will look for them.

## Related Docs

- [01-working-model.md](/Users/jameshassett/dev/FX_Analysis/docs/01-working-model.md)
- [02-analysis-workflow.md](/Users/jameshassett/dev/FX_Analysis/docs/02-analysis-workflow.md)
- [04-data-request-contract.md](/Users/jameshassett/dev/FX_Analysis/docs/04-data-request-contract.md)
- [07-systemacro-data-architecture.md](/Users/jameshassett/dev/FX_Analysis/docs/07-systemacro-data-architecture.md)
- [data_request_template.md](/Users/jameshassett/dev/FX_Analysis/docs/templates/data_request_template.md)
