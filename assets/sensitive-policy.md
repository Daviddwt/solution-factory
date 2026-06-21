# Sensitive Material Policy

The capability library may reference sensitive source files by path, but it must not copy sensitive bodies into reusable artifacts.

Allowed:

- File path
- File type
- Material title
- Short non-sensitive summary
- Product or capability tags
- Case label
- Confidence level

Not allowed:

- Contract body text
- Customer confidential clauses
- Exact pricing or payment amounts
- Invoice details
- Bank account details
- Personal identity information
- Private chat contents

When a useful source is sensitive, write a source reference and a safe evidence note such as:

```text
source_refs: [".../sensitive-source-folder/.../example-contract.pdf"]
evidence_note: "Existing delivery case. Use as internal proof only; do not quote contract text or amount."
```
