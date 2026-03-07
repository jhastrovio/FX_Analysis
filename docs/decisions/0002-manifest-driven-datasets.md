# Manifest-Driven Dataset Selection

This decision record explains why manifest-driven access exists. For the current operating model, start with [01-working-model.md](/Users/jameshassett/dev/FX_Analysis/docs/01-working-model.md) and [02-analysis-workflow.md](/Users/jameshassett/dev/FX_Analysis/docs/02-analysis-workflow.md).

## The Decision

Datasets are referenced via a manifest, not hard-coded file paths. You select a dataset by name (e.g., `model_signals`), and the system resolves the actual path from the manifest.

## Why This Matters

The FX data estate is organized, but organization can change. Paths might be restructured, datasets might move, naming conventions might evolve. If FX_Analysis hard-codes paths like `/FX_Data - General/clean/models_signals_systemacro/Models/`, it breaks when those paths change.

The manifest is the single source of truth. It knows:
- Where datasets actually live
- What their schemas are
- When they were last updated
- What their lifecycle status is

By referencing datasets by name, FX_Analysis stays decoupled from the physical organization of the data estate.

## How This Simplifies Analysis

Instead of thinking about paths, you think about datasets:

- "I need the model signals" → reference `model_signals`
- "I need end-of-day portfolios" → reference `eod_portfolio`
- "I need market changes" → reference `market_changes`

The manifest handles the rest. It knows the paths, validates schemas, checks freshness, and provides metadata.

This makes analysis code simpler and more portable. The same code works whether datasets are in OneDrive, on a network share, or in cloud storage—as long as the manifest points to the right place.

## Avoiding Coupling

Hard-coded paths create tight coupling:

- Code breaks when paths change
- Code assumes specific directory structures
- Code can't adapt to different environments
- Code becomes harder to test (need exact path structure)

Manifest-driven selection creates loose coupling:

- Code references logical names, not physical locations
- Path changes only require manifest updates
- Different environments can use different manifests
- Testing is easier (mock manifest entries)

## Implementation Note

The manifest itself is external to FX_Analysis. It's maintained by the data platform team and defines the authoritative view of available datasets. FX_Analysis consumes it, doesn't own it.

When you need a new dataset, you don't add it to FX_Analysis. You work with the producer team to add it to the manifest, then reference it by name.

## Practical Rule

If you find yourself writing a path like `/FX_Data - General/...` in code, stop. Look up the dataset name in the manifest and reference that instead. The only place paths should appear is in configuration that reads from the manifest.
