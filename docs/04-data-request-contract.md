# Data Request Contract

Use this contract when analysis needs data that does not yet exist, is not available at the required grain, or is missing fields needed for a sound result.

## When To Raise A Request

Raise a data request when:

- a governed dataset is missing entirely
- an existing dataset lacks required fields
- the available grain or keys do not support the analysis
- a schema change is needed upstream for repeatable analysis
- fixing the issue locally would turn FX_Analysis into a producer

Do not solve these gaps with ad hoc ingestion, repair, or dataset-production logic inside this repo.

## What A Request Must Contain

Each request should describe:

- the analytical problem being blocked
- why the current data is insufficient
- the proposed upstream dataset or schema change
- the expected grain and keys
- the required fields
- an example of how FX_Analysis will consume the result
- priority and owner

Use [data_request_template.md](/Users/jameshassett/dev/FX_Analysis/docs/templates/data_request_template.md).

## How To Frame The Need

Describe the analytical requirement, not the local workaround.

Good:
- "Need a governed daily dataset keyed by date and model_id with net returns and category fields so portfolio comparison can be repeated cleanly."

Bad:
- "Add a script in FX_Analysis that scrapes three folders, patches missing values, and writes a new permanent CSV."

## Expected Handoff Path

1. Identify the missing upstream input during analysis.
2. Write a request using the standard template.
3. Hand the request to the producer system owner.
4. Wait for the governed dataset or schema change to be delivered upstream.
5. Consume the new dataset through the normal manifest-driven path.

## After Upstream Delivery

Once the producer system implements the request:

- reference the new or updated governed dataset by manifest name
- update analysis code only as needed to consume it
- keep outputs temporary and local
- avoid copying upstream production logic back into FX_Analysis

## Rule Of Thumb

If the solution would create a permanent dataset, define a governed schema, or write back into `/FX_Data - General`, stop and raise a data request instead.
