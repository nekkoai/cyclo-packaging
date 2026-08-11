from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
PACKAGES = tuple(sorted(LOCK["sources"]))


class PackagingLayoutTests(unittest.TestCase):
    def test_lock_has_immutable_source_contracts(self) -> None:
        self.assertEqual(LOCK["schema_version"], 1)
        self.assertEqual(
            PACKAGES,
            ("cyclo", "cyclo-provider-pooler", "dcomp"),
        )
        for name, source in LOCK["sources"].items():
            with self.subTest(name=name):
                self.assertEqual(
                    set(source),
                    {
                        "repository",
                        "ref",
                        "commit",
                        "debian_revision",
                        "package_version",
                    },
                )
                self.assertRegex(source["repository"], r"^https://github\.com/.+\.git$")
                self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
                self.assertIsInstance(source["debian_revision"], int)
                self.assertGreaterEqual(source["debian_revision"], 1)
                self.assertRegex(source["package_version"], r"^[0-9][A-Za-z0-9.+~:-]*-[0-9]+$")

    def test_every_locked_source_has_a_complete_debian_overlay(self) -> None:
        for name in PACKAGES:
            with self.subTest(name=name):
                debian = ROOT / "packages" / name / "debian"
                for required in ("control", "changelog", "copyright", "rules"):
                    self.assertTrue((debian / required).is_file(), required)
                changelog = (debian / "changelog").read_text(encoding="utf-8")
                self.assertIn(f"({LOCK['sources'][name]['package_version']}) noble;", changelog)
                self.assertIn("Rules-Requires-Root: no", (debian / "control").read_text())

    def test_component_boundaries_do_not_create_host_services_or_credentials(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "packages").glob("*/debian/*")
            if path.is_file()
        )
        self.assertNotIn("systemd", combined.lower())
        self.assertNotIn("adduser", combined.lower())
        self.assertNotIn("useradd", combined.lower())
        for forbidden in ("postinst", "prerm", "postrm", "preinst"):
            self.assertFalse(any((ROOT / "packages").glob(f"*/debian/*.{forbidden}")))
        self.assertIn("never edits `host.conf`", (ROOT / "README.md").read_text())

    def test_build_tools_stage_overlays_instead_of_mutating_upstreams(self) -> None:
        fetch = (ROOT / "tools" / "fetch-sources").read_text(encoding="utf-8")
        build = (ROOT / "tools" / "build-packages").read_text(encoding="utf-8")
        self.assertIn("git", fetch)
        self.assertIn("checkout", fetch)
        self.assertIn('["git", "archive", "--format=tar", commit]', build)
        self.assertIn("shutil.copytree(overlay, destination / \"debian\"", build)
        self.assertIn("dpkg-buildpackage", build)
        refresh = (ROOT / "tools" / "refresh-latest").read_text(encoding="utf-8")
        self.assertIn('"--ref"', refresh)
        self.assertIn("overrides.get(name, locked_ref)", refresh)
        self.assertIn("requested main is unavailable", refresh)

    def test_workflow_refreshes_and_publishes_the_complete_suite(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "build-latest-debs.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("contents: write", workflow)
        for name in (
            "cyclo_branch",
            "dcomp_branch",
            "provider_pooler_branch",
        ):
            self.assertIn(f"{name}:", workflow)
        self.assertEqual(workflow.count("default: main"), 3)
        self.assertIn("push:\n    branches:\n      - main", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn("inputs.cyclo_branch || 'main'", workflow)
        self.assertIn("inputs.dcomp_branch || 'main'", workflow)
        self.assertIn("inputs.provider_pooler_branch || 'main'", workflow)
        self.assertIn("./tools/refresh-latest", workflow)
        self.assertIn("./tools/build-packages --output artifacts", workflow)
        self.assertIn("apt-utils", workflow)
        self.assertIn("build-essential", workflow)
        self.assertIn("./tools/build-apt-repository artifacts", workflow)
        self.assertIn("actions/upload-artifact@", workflow)
        self.assertIn("artifacts/sources.lock.json", workflow)
        self.assertIn("SHA256SUMS", workflow)
        self.assertIn("packaging-version-updates.patch || true", workflow)
        self.assertIn("zip -q -r", workflow)
        self.assertIn("find artifacts/apt-repository -maxdepth 1 -type f", workflow)
        self.assertIn("release_assets+=(\"$RELEASE_ARCHIVE\")", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("gh release edit", workflow)
        self.assertIn("--prerelease=false", workflow)
        self.assertNotIn("--prerelease\n", workflow)

    def test_cyclo_package_uses_the_global_state_launcher_contract(self) -> None:
        debian = ROOT / "packages" / "cyclo" / "debian"
        wrapper = (debian / "cyclo-wrapper").read_text(encoding="utf-8")
        rules = (debian / "rules").read_text(encoding="utf-8")

        self.assertIn("CYCLO_STATE_ROOT=${CYCLO_STATE_ROOT:-/var/lib/cyclo}", wrapper)
        self.assertIn("CYCLO_GLOBAL_STATE=1", wrapper)
        self.assertIn("/usr/lib/cyclo/cyclo-real", wrapper)
        self.assertEqual((debian / "cyclo.dirs").read_text(), "var/lib/cyclo\n")
        self.assertTrue((debian / "patches" / "global-state-mode.patch").is_file())
        self.assertIn("global-state-mode.patch", rules)
        self.assertIn("install -d -m 0777 debian/cyclo/var/lib/cyclo", rules)
        self.assertIn("chmod 0777 debian/cyclo/var/lib/cyclo", rules)

    def test_apt_repository_builder_emits_a_flat_github_release_repository(self) -> None:
        builder = (ROOT / "tools" / "build-apt-repository").read_text(
            encoding="utf-8"
        )
        self.assertIn("apt-ftparchive packages . > Packages", builder)
        self.assertIn("gzip -9n -k Packages", builder)
        self.assertIn("release . > Release", builder)
        self.assertNotIn("pool/main", builder)
        self.assertNotIn("dists/stable", builder)
        self.assertIn("releases/latest/download/ ./", builder)
        self.assertIn("apt-<run-id>", builder)
        self.assertIn('cat > "$artifacts/README.md"', builder)
        self.assertIn("# Cyclo Debian package artifact", builder)


if __name__ == "__main__":
    unittest.main()
