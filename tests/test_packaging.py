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
            ("cyclo-agent", "cyclo-provider-pooler", "dcomp"),
        )
        for name, source in LOCK["sources"].items():
            with self.subTest(name=name):
                self.assertEqual(
                    set(source),
                    {"repository", "ref", "commit", "package_version"},
                )
                self.assertRegex(source["repository"], r"^https://github\.com/.+\.git$")
                self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
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

    def test_manual_workflow_refreshes_and_publishes_the_complete_suite(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "build-latest-debs.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("contents: write", workflow)
        for name in (
            "cyclo_agent_branch",
            "dcomp_branch",
            "provider_pooler_branch",
        ):
            self.assertIn(f"{name}:", workflow)
        self.assertEqual(workflow.count("default: main"), 3)
        self.assertNotIn("push:", workflow)
        self.assertNotIn("pull_request:", workflow)
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
        self.assertIn("gh release create", workflow)
        self.assertIn("gh release upload", workflow)

    def test_apt_repository_builder_emits_a_consumable_unsigned_repository(self) -> None:
        builder = (ROOT / "tools" / "build-apt-repository").read_text(
            encoding="utf-8"
        )
        self.assertIn("apt-ftparchive packages pool/main", builder)
        self.assertIn("dists/stable/main/binary-amd64/Packages", builder)
        self.assertIn("APT::FTPArchive::Release::Suite", builder)
        self.assertIn("[trusted=yes] file:$repo stable main", builder)
        self.assertIn('cat > "$artifacts/README.md"', builder)
        self.assertIn("# Cyclo Debian package artifact", builder)


if __name__ == "__main__":
    unittest.main()
