import csv
import tempfile
import unittest
from pathlib import Path

from option_lab.cboe import convert


class CboeImportTest(unittest.TestCase):
    def test_standard_quotes_and_duplicate_day_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "day.csv"
            fields = ["underlying_symbol", "quote_date", "root", "expiration", "strike",
                      "option_type", "bid_size_1545", "bid_1545", "ask_size_1545",
                      "ask_1545", "underlying_bid_1545", "underlying_ask_1545",
                      "trade_volume", "delivery_code"]
            base = dict(zip(fields, ["ABC", "2025-06-02", "ABC", "2025-07-18", "50",
                                     "C", "4", "0.20", "3", "0.23", "48", "48.02", "12", ""]))
            with source.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerow(base)
                writer.writerow({**base, "root": "ABC1"})
                writer.writerow({**base, "bid_size_1545": "0"})
            out = str(Path(directory) / "out")
            audit = convert([str(source)], out)
            self.assertEqual(audit["symbols"], {"ABC": 1})
            self.assertEqual(audit["counts"]["unusable_quote"], 1)
            self.assertEqual(audit["counts"]["index_or_nonstandard"], 1)
            with (Path(out) / "cboe_options.csv").open() as f:
                self.assertEqual(list(csv.DictReader(f))[0]["right"], "call")
            with self.assertRaisesRegex(ValueError, "Duplicate date"):
                convert([str(source), str(source)], out)


if __name__ == "__main__":
    unittest.main()
