# Working Model

FX_Analysis works as a thin analytics layer on top of governed FX datasets.

## Three-Layer Model

```text
Producer system
  -> governed datasets
  -> FX_Analysis
  -> ephemeral outputs
```

## Division Of Labor

- Producer system: owns authoritative datasets, schemas, lifecycle, validation, and permanent storage.
- FX_Analysis: owns research workflows, metrics, dashboards, exploratory comparisons, and temporary exports.
- Data request loop: turns missing analytical inputs into structured upstream requests instead of local data-engineering workarounds.

## How Data Is Selected

FX_Analysis should reference datasets by manifest name, not by hard-coded paths. The producer system remains the source of truth for dataset location, schema, and lifecycle metadata.

## Feedback Loop

```text
governed data
   -> analysis in FX_Analysis
   -> missing field or dataset discovered
   -> data request written
   -> producer system implements upstream
   -> new governed dataset becomes available
   -> FX_Analysis consumes it
```

## Practical Reading

- Start analysis from governed datasets.
- Keep derived outputs local and disposable.
- If the data needed for analysis does not exist, stop short of building it here and follow the [data request contract](/Users/jameshassett/dev/FX_Analysis/docs/04-data-request-contract.md).
