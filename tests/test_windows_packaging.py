"""Guard the signing order required for a valid Windows driver catalog."""

from pathlib import Path
import unittest


class TestWindowsDriverPackaging(unittest.TestCase):
    def test_signed_sys_is_hashed_before_the_catalog_is_signed(self):
        script = (Path(__file__).resolve().parents[1] / "windows" / "package-driver.ps1").read_text()
        sign_sys = script.index('signtool failed for spenvhid.sys')
        inf2cat = script.index('& $inf2cat "/driver:$out" "/os:10_X64"')
        sign_cat = script.index('signtool failed for spenvhid.cat')

        self.assertLess(sign_sys, inf2cat)
        self.assertLess(inf2cat, sign_cat)


if __name__ == "__main__":
    unittest.main()
