"""Exercise the actual workflow shell with Git fixtures and a fake Cargo boundary.

No Rust toolchain, network access, or third-party Python packages are needed.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"


def step_script(name):
    # Extract one literal run block from this workflow, not general YAML.
    step = WORKFLOW.read_text().split(f"      - name: {name}\n", 1)[1]
    block = step.split("        run: |\n", 1)[1]
    lines = []
    for line in block.splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:])
    return "\n".join(lines) + "\n"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "zellij-src"
        self.source.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Workflow test")
        self.git("config", "user.email", "test@example.invalid")
        (self.source / "value.txt").write_text("original\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.env = dict(os.environ, UPSTREAM_SHA=self.git("rev-parse", "HEAD").stdout.strip(),
                        GITHUB_STEP_SUMMARY=str(self.root / "summary"))

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.source, text=True,
                              capture_output=True, check=True)

    def run_step(self, name):
        return subprocess.run(["bash", "-c", step_script(name)], cwd=self.root,
                              env=self.env, text=True, capture_output=True)

    def apply(self):
        return self.run_step("Verify upstream revision and apply patches")

    def patch(self, filename, before="original", after="patched"):
        patches = self.root / "patches"
        patches.mkdir(exist_ok=True)
        (patches / filename).write_text(
            "diff --git a/value.txt b/value.txt\n"
            "--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n"
            f"-{before}\n+{after}\n")

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_patch_directory(self):
        self.assert_ok(self.apply())
        self.assertEqual(self.git("diff").stdout, "")

    def test_empty_patch_directory(self):
        (self.root / "patches").mkdir()
        self.assert_ok(self.apply())

    def test_added_patches_apply_in_filename_order(self):
        self.patch("002 second.patch", "first", "second")
        self.patch("001 first.patch", "original", "first")
        self.patch("003 disabled.patch.disabled", "second", "disabled")
        self.assert_ok(self.apply())
        self.assertEqual((self.source / "value.txt").read_text(), "second\n")

    def test_removing_patch_restores_upstream_on_fresh_build(self):
        self.patch("001.patch")
        self.assert_ok(self.apply())
        self.assertEqual((self.source / "value.txt").read_text(), "patched\n")
        (self.root / "patches/001.patch").unlink()
        self.git("reset", "--hard", "HEAD")  # disposable fixture only
        self.assert_ok(self.apply())
        self.assertEqual((self.source / "value.txt").read_text(), "original\n")

    def test_stale_patch_fails(self):
        self.patch("001.patch", "wrong-base", "patched")
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual((self.source / "value.txt").read_text(), "original\n")

    def test_wrong_revision_fails_before_patching(self):
        self.patch("001.patch")
        self.env["UPSTREAM_SHA"] = "0" * 40
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual((self.source / "value.txt").read_text(), "original\n")

    def prepare_plugins(self):
        assets = self.source / "zellij-utils/assets/plugins"
        assets.mkdir(parents=True)
        for name in ("bars", "future-plugin"):
            (assets / f"{name}.wasm").write_text("old embedded bytes")
            manifest = self.source / f"default-plugins/{name}/Cargo.toml"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(f'[package]\nname = "{name}"\n')
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        # Only Cargo is replaced: the real workflow must discover packages and
        # copy each returned WASM file into the actual embedding directory.
        cargo = fake_bin / "cargo"
        cargo.write_text(textwrap.dedent("""\
            #!/bin/bash
            set -euo pipefail
            printf '%s\\n' "$@" > cargo-args.txt
            if [[ "${FAIL_CARGO:-0}" == 1 ]]; then exit 1; fi
            mkdir -p target/wasm32-wasip1/release
            while (($#)); do
              if [[ "$1" == -p ]]; then
                shift
                printf 'rebuilt %s' "$1" > "target/wasm32-wasip1/release/$1.wasm"
              fi
              shift
            done
            """))
        cargo.chmod(0o755)
        self.env["PATH"] = str(fake_bin) + os.pathsep + self.env["PATH"]
        return assets

    def test_every_bundled_plugin_is_rebuilt_and_embedded(self):
        assets = self.prepare_plugins()
        self.assert_ok(self.run_step("Rebuild built-in plugins"))
        for name in ("bars", "future-plugin"):
            self.assertEqual((assets / f"{name}.wasm").read_text(), f"rebuilt {name}")
        args = (self.source / "cargo-args.txt").read_text().splitlines()
        self.assertEqual(args[:5], ["build", "--locked", "--release", "--target", "wasm32-wasip1"])

    def test_plugin_build_failure_does_not_copy_old_output(self):
        assets = self.prepare_plugins()
        self.env["FAIL_CARGO"] = "1"
        self.assertNotEqual(self.run_step("Rebuild built-in plugins").returncode, 0)
        self.assertEqual((assets / "bars.wasm").read_text(), "old embedded bytes")

    def test_shared_test_fixture_is_not_built(self):
        assets = self.prepare_plugins()
        fixture = assets / "fixture-shared-plugin-for-tests.wasm"
        fixture.write_text("test-only bytes")
        self.assert_ok(self.run_step("Rebuild built-in plugins"))
        self.assertEqual(fixture.read_text(), "test-only bytes")
        self.assertNotIn("fixture-shared-plugin-for-tests",
                         (self.source / "cargo-args.txt").read_text())

    def test_missing_plugin_source_fails_before_cargo(self):
        self.prepare_plugins()
        (self.source / "default-plugins/future-plugin/Cargo.toml").unlink()
        self.assertNotEqual(self.run_step("Rebuild built-in plugins").returncode, 0)
        self.assertFalse((self.source / "cargo-args.txt").exists())


if __name__ == "__main__":
    unittest.main()
