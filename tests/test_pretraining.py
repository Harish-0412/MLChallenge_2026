import sys
import unittest
import tempfile
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from normalization import comparison_key, latin_accent_key, entity_f05
from audit_dataset import key_sql, csv_scan, SOURCE_COLUMNS
import duckdb


class PretrainingTests(unittest.TestCase):
    def test_devanagari_marks_survive(self):
        self.assertEqual(comparison_key('आदित्य ट्रेडिंग प्रा. लि.'), 'आदित्य ट्रेडिंग प्रा लि')

    def test_accent_fold_does_not_destroy_indic(self):
        self.assertEqual(latin_accent_key('École आदित्य'), 'ecole आदित्य')

    def test_numbers_survive(self):
        self.assertEqual(comparison_key('No. 5-105 / 0012'), 'no 5 105 0012')

    def test_idempotence(self):
        for text in ['École', 'आदित्य ट्रेडिंग', 'A & B Ltd.', '  5 bis\tRue  ']:
            self.assertEqual(comparison_key(comparison_key(text)), comparison_key(text))

    def test_sql_python_contract(self):
        con=duckdb.connect()
        for text in ['École', 'E\u0301cole', 'आदित्य ट्रेडिंग प्रा. लि.', 'महाराष्ट्र', 'A & B Ltd.', '', '  No.5-105\t', 'a_b']:
            result=con.execute(f'SELECT {key_sql("value")} FROM (SELECT ? AS value)',[text]).fetchone()[0]
            self.assertEqual(result,comparison_key(text))
        con.close()

    def test_singleton_and_empty_predictions(self):
        self.assertEqual(entity_f05([],[]),1.0)
        self.assertEqual(entity_f05([],['x']),0.0)
        self.assertEqual(entity_f05(['x'],[]),0.0)

    def test_official_metric_example(self):
        self.assertAlmostEqual(entity_f05(['a','b'],['a','b','c']),5/7)

    def test_false_positive_cost(self):
        self.assertLess(entity_f05(['a','b'],['a','b','c']),entity_f05(['a','b'],['a']))

    def test_parser_preserves_literal_na_and_empty_address(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.tsv'
            with path.open('w',encoding='utf-8',newline='') as stream:
                writer=csv.writer(stream,delimiter='\t')
                writer.writerow(SOURCE_COLUMNS)
                writer.writerow(['S2-001','NA','','France'])
                writer.writerow(['S2-002','आदित्य','Unit\t12, Road','India'])
            con=duckdb.connect()
            rows=con.execute(f'SELECT * FROM {csv_scan(path,SOURCE_COLUMNS)} ORDER BY entity_id').fetchall()
            con.close()
            self.assertEqual(rows,[('S2-001','NA','','France'),('S2-002','आदित्य','Unit\t12, Road','India')])

    def test_parser_rejects_missing_column(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.tsv'
            path.write_text('\t'.join(SOURCE_COLUMNS)+'\nS1-1\tAcme\tIndia\n',encoding='utf-8')
            con=duckdb.connect()
            with self.assertRaises(duckdb.InvalidInputException):
                con.execute(f'SELECT * FROM {csv_scan(path,SOURCE_COLUMNS)}').fetchall()
            con.close()

    def test_accent_composition_equivalence(self):
        self.assertEqual(comparison_key('E\u0301cole'),comparison_key('École'))


if __name__=='__main__':
    unittest.main()
