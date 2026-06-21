# Review Gates

## Gate 1: Capability Library Review

Reviewer confirms:

- Which capabilities are safe to present externally.
- Which capabilities are internal-only evidence.
- Which capabilities require product owner confirmation.
- Which capability names should be standardized.

## Gate 2: Requirement And Match Review

Reviewer confirms:

- Requirements match the customer scenario.
- Pain points and target states are not invented.
- Capability matches respect company delivery boundaries.
- `unclear` and `custom_dev` items are visible instead of hidden.

## Gate 3: PPT Script Review

Reviewer confirms:

- Each page has a clear message.
- Each page has supporting evidence and capability links.
- Visual type matches the content.
- The script is ready for NotebookLM/image PPT rendering.

No downstream PPT rendering should start before Gate 3 passes.
