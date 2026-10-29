import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from clean_csv import ValidationError, clean_bytes, make_payload


def parsed(raw):
    return list(csv.reader(io.StringIO(raw.decode("utf-8"), newline="")))


class CleanupTests(unittest.TestCase):
    def test_defaults_preserve_values_duplicates_and_embedded_newlines(self):
        raw = b'id,note,amount\r\n001,"A, B\r\nnext", 04.00 \r\n001,"A, B\r\nnext", 04.00 \r\n'
        out, report, _ = clean_bytes(raw)
        self.assertEqual(parsed(out), [['id', 'note', 'amount'],
                         ['001', 'A, B\r\nnext', ' 04.00 '],
                         ['001', 'A, B\r\nnext', ' 04.00 ']])
        self.assertEqual((report['input_rows'], report['output_rows']), (2, 2))
        self.assertEqual(report['cells_trimmed'], 0)
        self.assertEqual(report['duplicate_rows_removed'], 0)

    def test_explicit_trim_empty_and_deduplicate_counts(self):
        raw = b'Name,Code\n A ,001\nA,001\n ,\nB,002\n'
        out, report, _ = clean_bytes(raw, {'trim_cells': True, 'drop_empty_rows': True,
                                          'deduplicate': True})
        self.assertEqual(parsed(out), [['Name', 'Code'], ['A', '001'], ['B', '002']])
        self.assertEqual((report['input_rows'], report['output_rows']), (4, 2))
        self.assertEqual((report['empty_rows_removed'], report['duplicate_rows_removed']), (1, 1))
        self.assertEqual(report['cells_trimmed'], 2)

    def test_header_map_only_leaves_cell_values_unchanged(self):
        out, report, _ = clean_bytes(b' Name ,Code\n A ,001\n', {'header_map': {' Name ': 'name'}})
        self.assertEqual(parsed(out), [['name', 'Code'], [' A ', '001']])
        self.assertEqual(report['headers_renamed'], 1)
        self.assertEqual(report['cells_trimmed'], 0)

    def test_header_collision_and_unknown_mapping_refused(self):
        for mapping in ({'A': 'B'}, {'C': 'D'}):
            with self.assertRaises(ValidationError):
                clean_bytes(b'A,B\n1,2\n', {'header_map': mapping})

    def test_empty_and_duplicate_headers_refused(self):
        for raw in (b'A,A\n1,2\n', b',B\n1,2\n'):
            with self.assertRaises(ValidationError):
                clean_bytes(raw)

    def test_malformed_quotes_and_row_width_refused(self):
        for raw in (b'A,B\n"not closed,2', b'A,B\n1,2,3\n'):
            with self.assertRaises(ValidationError):
                clean_bytes(raw)

    def test_blank_records_and_empty_fields_have_explicit_behavior(self):
        raw = b'A,B\n\n,\n , \nNA,0\n'
        out, report, _ = clean_bytes(raw)
        self.assertEqual(parsed(out), [['A', 'B'], [], ['', ''], [' ', ' '], ['NA', '0']])
        self.assertEqual(report['output_rows'], 4)
        out, report, _ = clean_bytes(raw, {'drop_empty_rows': True})
        self.assertEqual(parsed(out), [['A', 'B'], [' ', ' '], ['NA', '0']])
        self.assertEqual(report['empty_rows_removed'], 2)

    def test_literal_carriage_return_and_quoted_quote_preserved(self):
        out, _, _ = clean_bytes(b'A,B\r\n"x\ry","a""b"\r\n')
        self.assertEqual(parsed(out), [['A', 'B'], ['x\ry', 'a"b']])

    def test_limit_boundaries(self):
        clean_bytes(b'A\n' + b'v\n' * 1000)
        for raw in (b'A\n' + b'v\n' * 1001, b'A\n' + b'x' * 149999,
                    (','.join('c'+str(i) for i in range(21))+'\n').encode()):
            with self.assertRaises(ValidationError):
                clean_bytes(raw)

    def test_single_large_field_within_advertised_byte_limit(self):
        raw = b'A\n' + b'x' * 149998
        out, report, _ = clean_bytes(raw)
        self.assertEqual(parsed(out), [['A'], ['x' * 149998]])
        self.assertEqual(report['output_rows'], 1)

    def test_no_truthy_string_options_or_unknown_options(self):
        for rules in ({'trim_cells': 'false'}, {'drop_empty_rows': 1}, {'drop_columns': ['A']}):
            with self.assertRaises(ValidationError):
                clean_bytes(b'A\n001\n', rules)

    def test_tab_delimiter_utf8_bom_and_repeatability(self):
        raw = b'\xef\xbb\xbfA\tB\n001\t 2 \n'
        a = clean_bytes(raw, {'delimiter': '\t'})
        self.assertEqual(a, clean_bytes(raw, {'delimiter': '\t'}))
        self.assertEqual(a[0], b'A\tB\r\n001\t 2 \r\n')

    def test_payload_contains_reproducer_and_fits_mailbox(self):
        payload, report = make_payload(b'A,B\n001,"A, B"\n')
        files = {x['name']: x['content'] for x in payload['files']}
        self.assertIn('clean_csv.py', files)
        self.assertEqual(json.loads(files['summary.json']), report)
        self.assertLess(len(json.dumps(payload, ensure_ascii=False).encode('utf-8')), 1_000_000)

    def test_cli_reproduces_and_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = b'A,B\n 001 ,"x,y"\n'
            (root/'input.csv').write_bytes(raw)
            (root/'rules.json').write_text('{"trim_cells": true}', encoding='utf-8')
            cmd = [sys.executable, str(Path(__file__).with_name('clean_csv.py')),
                   str(root/'input.csv'), '--rules', str(root/'rules.json'),
                   '--output-dir', str(root/'output')]
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(parsed((root/'output/cleaned.csv').read_bytes()),
                             [['A', 'B'], ['001', 'x,y']])
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(parsed((root/'output/cleaned.csv').read_bytes()),
                             [['A', 'B'], ['001', 'x,y']])
            reproduce = [sys.executable, str(root/'output/clean_csv.py'), str(root/'input.csv'),
                         '--rules', str(root/'output/rules.json'), '--output-dir', str(root/'again')]
            run = subprocess.run(reproduce, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual((root/'output/cleaned.csv').read_bytes(), (root/'again/cleaned.csv').read_bytes())

    def test_cli_validation_failure_creates_no_delivery(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'input.csv').write_bytes(b'A,B\n1,2,3\n')
            run = subprocess.run([sys.executable, str(Path(__file__).with_name('clean_csv.py')),
                                  str(root/'input.csv'), '--output-dir', str(root/'output')],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertFalse((root/'output').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
