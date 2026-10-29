# Quiet Current Workbench

Small, reproducible data jobs by Quiet Current, a human-operated, AI-assisted service. Sales help fund a private project.

## One small CSV cleanup: 3 USDC

Have a public or synthetic CSV that needs a careful cleanup? For **3 USDC on Base**, we handle one file with up to **1,000 data records, 20 columns and 150,000 bytes**. Choose only the operations you need:

- Trim whitespace at the edges of data cells.
- Rename headers using your exact mapping.
- Remove entirely empty records.
- Remove exact duplicate records, keeping the first.

Leading zeroes, quoted commas and embedded line breaks remain cell values. Other values and retained row order stay unchanged. Empty means an empty string after requested trimming; `NULL`, `NA` and `0` remain ordinary values. CSV quoting and record endings are normalized. Ambiguous headers or malformed rows are reported for clarification.

You receive the cleaned CSV, change counts, input/output hashes, exact rules, a dependency-free Python reproducer and instructions. One correction within the agreed input and rules is included. A new dataset or transformation needs a new agreement.

**[Request a cleanup](https://github.com/quietcurrent/quiet-current-workbench/issues)** with your public sample, selected operations and required date. We explicitly agree the scope, total price, delivery date and payment steps before payment. An inquiry is free and creates no accepted order. There is no automatic checkout or always-on fulfillment.

These are public channels. Do not submit personal information, confidential material, credentials or keys. Share only data you may publish. Agents need their operator's authorization to pay.

## See the method

The included example is synthetic, not a customer job. It starts with four records: one duplicate, one empty record and two retained records. Requested cleanup produces two records while preserving `001`, `002`, a quoted comma and a line break.

- [Original CSV](sample-input.csv) and [explicit rules](sample-rules.json)
- [Cleaned CSV](sample-output/cleaned.csv) and [change report](sample-output/summary.json)
- [Python helper](clean_csv.py) and [tests](test_clean_csv.py)

You can use the helper yourself at no charge with Python 3.10 or newer:

```text
python clean_csv.py sample-input.csv --rules sample-rules.json --output-dir my-output
python -m unittest -v test_clean_csv.py
```

The output directory must not already exist. The helper uses only Python's standard library and performs no network requests. With no rules file, no cleanup operations are enabled. Output is UTF-8 with CRLF record endings; cell contents remain intact except for explicitly selected transformations.

The paid service covers applying and checking the agreed rules for your file. It does not sell exclusive access to this public helper. You retain rights to your input and may use and modify the delivered script and output.

## Other work

For custom agent comics, visit the [Quiet Current art portfolio](https://github.com/quietcurrent/quiet-current-art). No clients, sales or earnings are implied by the synthetic sample here.
