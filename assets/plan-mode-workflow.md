# Solution Factory Plan Mode Workflow

This plugin must start every new solution-production project with a Plan-mode intake before generating artifacts.

## Rule

Do not generate requirement packs, PPT scripts, architecture prompts, or NotebookLM prompts until the operator has reviewed the intake summary and approved the next step.

## Plan-Mode Stages

1. Project framing
   - Confirm project name, customer, industry, audience, proposal purpose, expected output, delivery deadline, and presentation depth.
   - Confirm whether the output is a requirement analysis, solution proposal, architecture deck, image PPT prompt, editable PPTX, or all of them.

2. Material collection
   - Ask the operator to upload or point to all materials before analysis.
   - Group materials into customer background, customer requirements, existing systems/interfaces, company products/FRS, company cases, company profile, pricing/commercial boundaries, and PPT style references.
   - If the operator only provides partial materials, record what is missing and ask whether to proceed with assumptions.

3. Source and sensitivity policy
   - Confirm which folders/files are approved sources.
   - Apply `assets/sensitive-policy.md`: store summaries, tags, source paths, and capability statements only; do not copy contracts, exact prices, invoice details, or personal identity data.
   - Mark unsupported claims as assumptions or open questions.

4. Style-template intake
   - If the operator needs a specific PPT style, request reference screenshots, PPTX, PDF, or images.
   - If no style reference is provided, use `assets/notebooklm-image-ppt-style.zh-CN.md`.
   - If references are provided, run `style-template-agent` before PPT scripting or NotebookLM prompt generation.

5. Production plan
   - Summarize materials received, missing materials, key assumptions, intended outputs, review gates, and proposed sub-agent work split.
   - Ask for approval before executing.

6. Artifact production
   - Use the orchestrator and sub-agents to produce the standard artifacts.
   - Keep the source of truth in structured artifacts, not in rendered PPTs.

7. Review gates
   - Gate 1: company capability library.
   - Gate 2: requirement pack and capability match matrix.
   - Gate 3: implementation blueprint and page-level PPT script.
   - Gate 4: scenario or overall NotebookLM prompt before rendering.

8. Handoff
   - Give image-PPT agents only the relevant NotebookLM prompt.
   - Give editable-PPT agents the approved image PPT, script, and visual plan.
   - Preserve the structured artifacts for future reuse.

## Minimum Intake Questions

- What is the project/customer name?
- What industry and business domain does it belong to?
- Who is the audience: customer executives, business department, IT department, procurement, or internal review?
- What is the intended output: demand analysis, solution proposal, PPT script, image PPT prompt, editable PPT, or a complete package?
- What materials are available now, and which ones are still missing?
- Are there approved company product/FRS/case materials that must be used?
- Are there materials that must not be copied, quoted, or exposed?
- Are there existing customer systems, APIs, databases, devices, or third-party apps that must be integrated?
- Does the PPT need to follow a specific style? If yes, upload reference PPT/PDF/screenshots/images.
- What must be confirmed with the customer before making commitments?

