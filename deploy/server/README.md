# Solution Factory Server CLI

This lightweight server bundle exposes the server-safe script-production path without a browser workbench.

## Scope

```text
company knowledge base + customer materials + operator instructions
-> page-level PPT scripts
-> page-level image-production prompts
-> script-package.zip
```

It does not generate image PPTX or editable PPTX.

## Quick Check

```bash
./deploy/server/healthcheck.sh
```

## Create A Job

```bash
./deploy/server/run-cli.sh init \
  --output-root /srv/solution-factory-workbench \
  --requester "Operator" \
  --title "某项目解决方案汇报" \
  --pages 12 \
  --source /srv/uploads/customer \
  --knowledge-base /srv/knowledge/company-baseline
```

## Next Steps

Use `run-model`, `import-script`, `validate`, and `package` from `scripts/solution_factory_workbench.py`.
