"""Bounded, opt-in CSV cleanup. Standard library only; no network access."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

MAX_INPUT_BYTES = 150_000
MAX_ROWS = 1_000
MAX_COLUMNS = 20
MAX_PAYLOAD_BYTES = 1_000_000
csv.field_size_limit(MAX_INPUT_BYTES)
RULE_KEYS = {"delimiter", "trim_cells", "header_map", "drop_empty_rows", "deduplicate"}


class ValidationError(ValueError):
    """The input cannot be processed without an unsupported assumption."""


def normalize_rules(supplied):
    if not isinstance(supplied, dict) or set(supplied) - RULE_KEYS:
        raise ValidationError("Rules must be an object containing documented options only.")
    rules = {"delimiter": ",", "trim_cells": False, "header_map": {},
             "drop_empty_rows": False, "deduplicate": False}
    rules.update(supplied)
    delimiter = rules["delimiter"]
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '"\r\n\0':
        raise ValidationError("Delimiter must be one character other than quote, newline or NUL.")
    for key in ("trim_cells", "drop_empty_rows", "deduplicate"):
        if not isinstance(rules[key], bool):
            raise ValidationError(key + " must be a JSON boolean.")
    mapping = rules["header_map"]
    if not isinstance(mapping, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in mapping.items()
    ):
        raise ValidationError("header_map must map exact existing headers to nonblank strings.")
    return rules


def clean_bytes(raw, supplied_rules=None):
    """Return canonical UTF-8 CSV, deterministic summary and effective rules.

    No operation is enabled by default. Empty means a zero-length string, not
    NULL/NA/0; whitespace is empty only after explicitly requested trimming.
    Deduplication compares complete rows after the requested transformations.
    Blank physical records count as data rows and stay blank unless removed.
    """
    if len(raw) > MAX_INPUT_BYTES:
        raise ValidationError("Input exceeds 150,000 bytes.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("Input must be UTF-8.") from exc
    if "\0" in text:
        raise ValidationError("NUL characters are not supported.")
    rules = normalize_rules({} if supplied_rules is None else supplied_rules)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""),
                               delimiter=rules["delimiter"], strict=True))
    except csv.Error as exc:
        raise ValidationError("Malformed CSV: " + str(exc)) from exc
    if not rows or not rows[0]:
        raise ValidationError("CSV must start with a header row.")
    header, records = rows[0], rows[1:]
    if len(header) > MAX_COLUMNS:
        raise ValidationError("Input exceeds 20 columns.")
    if len(records) > MAX_ROWS:
        raise ValidationError("Input exceeds 1,000 data rows.")
    if any(not name.strip() for name in header) or len(set(header)) != len(header):
        raise ValidationError("Input headers must be nonblank and unique.")
    unknown = set(rules["header_map"]) - set(header)
    if unknown:
        raise ValidationError("Header mapping references unknown source headers.")
    final_header = [rules["header_map"].get(name, name) for name in header]
    if len(set(final_header)) != len(final_header):
        raise ValidationError("Requested header mapping creates a collision.")
    for index, row in enumerate(records, 1):
        if row and len(row) != len(header):
            raise ValidationError("Data row %d has %d fields; expected %d."
                                  % (index, len(row), len(header)))
    output, seen = [], set()
    dropped_empty = dropped_duplicate = trimmed_cells = 0
    for row in records:
        transformed = [cell.strip() for cell in row] if rules["trim_cells"] else row[:]
        trimmed_cells += sum(a != b for a, b in zip(row, transformed))
        if rules["drop_empty_rows"] and all(cell == "" for cell in transformed):
            dropped_empty += 1
            continue
        key = tuple(transformed)
        if rules["deduplicate"] and key in seen:
            dropped_duplicate += 1
            continue
        seen.add(key)
        output.append(transformed)
    # CRLF records ensure embedded CR and LF are always quoted by csv.writer.
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter=rules["delimiter"], lineterminator="\r\n")
    writer.writerow(final_header)
    writer.writerows(output)
    cleaned = stream.getvalue().encode("utf-8")
    summary = {
        "input_rows": len(records), "output_rows": len(output),
        "columns": len(header), "empty_rows_removed": dropped_empty,
        "duplicate_rows_removed": dropped_duplicate,
        "cells_trimmed": trimmed_cells,
        "headers_renamed": sum(a != b for a, b in zip(header, final_header)),
        "row_order_preserved": True,
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "output_sha256": hashlib.sha256(cleaned).hexdigest(),
        "empty_value_rule": "Only zero-length strings; after trimming if explicitly selected.",
        "duplicate_rule": "Complete exact rows after requested transformations; first retained.",
        "serialization": "UTF-8 without BOM; CRLF record endings; CSV quoting may change."
    }
    return cleaned, summary, rules


def json_text(value):
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def make_payload(raw, supplied_rules=None):
    cleaned, summary, rules = clean_bytes(raw, supplied_rules)
    files = {
        "cleaned.csv": cleaned.decode("utf-8"),
        "summary.json": json_text(summary),
        "rules.json": json_text(rules),
        "clean_csv.py": Path(__file__).read_text(encoding="utf-8"),
        "REPRODUCE.txt": (
            "Save your original input unchanged as input.csv. Run:\n"
            "python clean_csv.py input.csv --rules rules.json --output-dir reproduced\n"
            "The output directory must not already exist. No dependencies or network calls.\n"
            "Compare SHA-256 of reproduced/cleaned.csv with summary.json output_sha256.\n"
            "CSV quoting/record endings are canonicalized; unrequested cell values stay unchanged.\n"
        ),
    }
    payload = {"files": [{"name": name, "content": content} for name, content in files.items()]}
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValidationError("Delivery payload would exceed 1 MB.")
    return payload, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--rules", type=Path, help="JSON options; omitted means no transformations")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        # Read at most the advertised limit plus one byte before validation.
        with args.input_csv.open("rb") as source:
            raw = source.read(MAX_INPUT_BYTES + 1)
        rules = json.loads(args.rules.read_text(encoding="utf-8")) if args.rules else {}
        payload, summary = make_payload(raw, rules)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        for item in payload["files"]:
            (args.output_dir / item["name"]).write_bytes(item["content"].encode("utf-8"))
        (args.output_dir / "delivery-payload.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="")
    except (OSError, ValueError) as exc:
        parser.exit(2, "Refused: " + str(exc) + "\n")
    print(json.dumps({"input_rows": summary["input_rows"],
                      "output_rows": summary["output_rows"],
                      "output_directory": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
