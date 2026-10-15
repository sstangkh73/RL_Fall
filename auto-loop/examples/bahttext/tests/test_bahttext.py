import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bahttext import baht_text  # noqa: E402


class TestBahtText(unittest.TestCase):
    def check(self, cases):
        for amount, expected in cases:
            with self.subTest(amount=amount):
                self.assertEqual(baht_text(amount), expected)

    def test_units(self):
        self.check([
            (0, "ศูนย์บาทถ้วน"),
            (1, "หนึ่งบาทถ้วน"),
            (5, "ห้าบาทถ้วน"),
        ])

    def test_tens(self):
        self.check([
            (10, "สิบบาทถ้วน"),
            (11, "สิบเอ็ดบาทถ้วน"),
            (20, "ยี่สิบบาทถ้วน"),
            (21, "ยี่สิบเอ็ดบาทถ้วน"),
            (99, "เก้าสิบเก้าบาทถ้วน"),
        ])

    def test_hundreds_and_up(self):
        self.check([
            (100, "หนึ่งร้อยบาทถ้วน"),
            (101, "หนึ่งร้อยเอ็ดบาทถ้วน"),
            (111, "หนึ่งร้อยสิบเอ็ดบาทถ้วน"),
            (1234, "หนึ่งพันสองร้อยสามสิบสี่บาทถ้วน"),
            (20021, "สองหมื่นยี่สิบเอ็ดบาทถ้วน"),
            (350000, "สามแสนห้าหมื่นบาทถ้วน"),
        ])

    def test_millions(self):
        self.check([
            (1000000, "หนึ่งล้านบาทถ้วน"),
            (2500000, "สองล้านห้าแสนบาทถ้วน"),
            (11000000, "สิบเอ็ดล้านบาทถ้วน"),
            (21000000, "ยี่สิบเอ็ดล้านบาทถ้วน"),
            (1000000000000, "หนึ่งล้านล้านบาทถ้วน"),
        ])

    def test_satang(self):
        self.check([
            (0.01, "หนึ่งสตางค์"),
            (0.75, "เจ็ดสิบห้าสตางค์"),
            (21.5, "ยี่สิบเอ็ดบาทห้าสิบสตางค์"),
            (Decimal("1234.25"), "หนึ่งพันสองร้อยสามสิบสี่บาทยี่สิบห้าสตางค์"),
            (Decimal("100.11"), "หนึ่งร้อยบาทสิบเอ็ดสตางค์"),
        ])

    def test_rounding(self):
        self.check([
            (Decimal("1.005"), "หนึ่งบาทหนึ่งสตางค์"),
            (Decimal("0.999"), "หนึ่งบาทถ้วน"),
        ])

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            baht_text(-1)


if __name__ == "__main__":
    unittest.main()
