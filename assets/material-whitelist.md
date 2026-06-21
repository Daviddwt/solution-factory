# Material Whitelist

首版只扫描与解决方案生产直接相关的企业微盘目录。

Default Enterprise WeDrive organization root should be configured by each operator. On macOS, the path usually looks like:

```text
<operator-enterprise-wedrive-root>
```

Allowed buckets:

- `解决方案与销售部/A.售前方案`
- `解决方案与销售部/C.公司概况简介`
- `产品部/产品标准文档`
- `产品部/敢为云解决方案&案例&产品手册`

Local workspace bucket:

- `<current-project>/knowledge_base_md`
- Any operator-provided project knowledge-base folder approved during Plan-mode intake

Do not scan the whole Enterprise WeDrive root. Folders such as contracts, invoices, personal reimbursement files, broad project archives, and temporary uploads are outside the default scope.
