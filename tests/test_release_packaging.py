"""Release safety: reject wrong source, debug artifacts and accidental overwrite."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from release.package_android import package


class ReleasePackagingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.commit = self.root / "source-commit.txt"
        self.commit.write_text("a" * 40 + "\n")
        self.apk = self.root / "input.apk"
        self.apk.write_bytes(b"fixture")
        self.tools = self.root / "build-tools"
        self.output = self.root / "release"

    def invoke(self):
        return package(self.apk, self.commit, self.tools, self.output)

    def test_wrong_commit_is_rejected_before_signing(self):
        with patch("release.package_android.run", return_value="b" * 40):
            with self.assertRaisesRegex(ValueError, "source commit"):
                self.invoke()
        self.assertFalse(self.output.exists())

    def test_uncommitted_source_is_rejected(self):
        with patch("release.package_android.run", side_effect=["a" * 40, " M server/protocol.py"]):
            with self.assertRaisesRegex(ValueError, "Commit tracked changes"):
                self.invoke()

    def test_debug_apk_is_rejected_even_with_matching_version(self):
        metadata = "package: name='com.spenbridge.app' versionCode='2' versionName='1.1.0-rc1'\napplication-debuggable\n"
        with patch("release.package_android.run", side_effect=["a" * 40, "", metadata]):
            with self.assertRaisesRegex(ValueError, "non-debuggable"):
                self.invoke()

    def test_wrong_version_or_application_is_rejected(self):
        for metadata in [
            "package: name='com.spenbridge.app' versionCode='1' versionName='1.0.0'",
            "package: name='com.spenbridge.app.uiaudit' versionCode='2' versionName='1.1.0-rc1'",
        ]:
            with self.subTest(metadata=metadata):
                with patch("release.package_android.run", side_effect=["a" * 40, "", metadata]):
                    with self.assertRaisesRegex(ValueError, "release variant"):
                        self.invoke()

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("existing release")
        metadata = "package: name='com.spenbridge.app' versionCode='2' versionName='1.1.0-rc1'"
        environment = {key: "fixture" for key in ["SPEN_KEYSTORE", "SPEN_KEY_ALIAS", "SPEN_STORE_PASSWORD", "SPEN_KEY_PASSWORD"]}
        with patch("release.package_android.run", side_effect=["a" * 40, "", metadata]), patch.dict("os.environ", environment):
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.invoke()
        self.assertEqual(marker.read_text(), "existing release")

    def test_wrong_signer_leaves_no_release_outputs(self):
        metadata = "package: name='com.spenbridge.app' versionCode='2' versionName='1.1.0-rc1'"
        environment = {key: "fixture" for key in ["SPEN_KEYSTORE", "SPEN_KEY_ALIAS", "SPEN_STORE_PASSWORD", "SPEN_KEY_PASSWORD"]}
        responses = ["a" * 40, "", metadata, "", "", "Signer #1 certificate SHA-256 digest: " + "0" * 64]
        with patch("release.package_android.run", side_effect=responses), patch.dict("os.environ", environment):
            with self.assertRaisesRegex(ValueError, "pinned release identity"):
                self.invoke()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".spen-sign-*")), [])
