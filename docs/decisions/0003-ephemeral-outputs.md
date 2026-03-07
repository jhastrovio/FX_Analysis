# Ephemeral Outputs

This decision record explains why outputs stay temporary. For the current contributor-facing guidance, start with [00-overview.md](/Users/jameshassett/dev/FX_Analysis/docs/00-overview.md) and [03-read-only-contract.md](/Users/jameshassett/dev/FX_Analysis/docs/03-read-only-contract.md).

## The Decision

All outputs from FX_Analysis are temporary analysis artifacts written to a local `outputs/` directory. They are not written back to the governed data store at `/FX_Data - General`.

## Why Outputs Are Temporary

FX_Analysis produces derived data: consolidated matrices, calculated metrics, filtered views, visualizations. These are analysis artifacts, not source data.

Source data lives in `/FX_Data - General` and is authoritative. Analysis outputs are:
- **Derived**: Calculated from source data
- **Regenerable**: Can be recreated by re-running analysis
- **Context-specific**: Tied to particular analysis questions
- **Temporary**: Not needed long-term

Writing these back to the governed store would:
- Mix derived data with source data
- Create confusion about what's authoritative
- Clutter the data estate with temporary artifacts
- Require lifecycle management for things that don't need it

## Why Not Write Back

The governed data store is for permanent, authoritative datasets. It has:
- Schema definitions and validation
- Lifecycle management (creation, updates, archival)
- Quality guarantees and reconciliation
- Access controls and audit trails

Analysis outputs don't need any of this. They're temporary, regenerable, and specific to the analysis being performed.

Writing them back would also violate the read-only boundary. FX_Analysis is a consumer, not a producer. It doesn't create permanent datasets—that's the producer's job.

## What This Means Practically

When you run analysis:
- Results go to `outputs/` directory
- Files can be deleted and regenerated
- No versioning or archival needed
- No schema definitions required
- No lifecycle management

If you need to share results:
- Export from `outputs/` to wherever needed
- Or point others to re-run the analysis
- Or archive outputs externally if really needed

If you need permanent storage:
- That's a signal the output should be a real dataset
- Work with producer team to create it properly
- Then reference it via manifest like any other dataset

## The Local Outputs Directory

The `outputs/` directory is:
- Local to the FX_Analysis repository
- Gitignored (not versioned)
- Ephemeral (can be cleared anytime)
- User-managed (you decide what to keep)

It's a workspace, not a data store. Use it freely for analysis artifacts, knowing they're temporary.

## Practical Rule

If you find yourself wanting to write analysis results to `/FX_Data - General`, ask: "Is this a permanent, authoritative dataset?" If yes, it belongs in the producer repository, not as an FX_Analysis output. If no, it goes in `outputs/` and stays temporary.
