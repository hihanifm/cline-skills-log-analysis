"""
test_pipeline.py — Minimal pipeline tests for cline-skills-log-analysis.

Three test classes, each building on the previous:

  TestLogFilter      — unit tests for log_filter.filter_file() directly
  TestTemplateRunner — tests template_runner.run_template() against the
                       wakelock template and logcat fixture
  TestE2EPipeline    — subprocess-level test of the full two-stage pipeline
                       (context_builder_agent → log_synthesizer_agent)

Skip conditions:
  - All tests skip if ripgrep (rg) is not installed.
  - TestE2EPipeline synthesizer sub-test uses the openai backend when
    LLM_API_KEY is set in the environment, otherwise falls back to the
    cline backend (placeholder markers, no network call).

Run:
    # Layer 1 + 2 only:
    python3 -m pytest tests/test_pipeline.py -v -k "not E2E"

    # Full suite:
    python3 -m pytest tests/test_pipeline.py -v

    # Without pytest:
    python3 -m unittest tests.test_pipeline -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# ── Paths ─────────────────────────────────────────────────────────────────────

# Ensure Homebrew bin is in PATH so both shutil.which and subprocesses find rg.
_HOMEBREW_BIN = "/opt/homebrew/bin"
if _HOMEBREW_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _HOMEBREW_BIN + os.pathsep + os.environ.get("PATH", "")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
LOGCAT_FIXTURE = os.path.join(FIXTURES_DIR, "logcat_sample.txt")
BUGREPORT_FIXTURE = os.path.join(FIXTURES_DIR, "bugreport_sample.txt")

WAKELOCK_TEMPLATE = os.path.join(
    REPO_ROOT, "skills", "template-library", "templates", "log", "wakelock.yaml"
)
BATTERY_WORKFLOW = os.path.join(
    REPO_ROOT, "skills", "workflow-creator", "examples", "battery-troubleshooting.md"
)
CONTEXT_BUILDER = os.path.join(
    REPO_ROOT, "skills", "workflow-orchestrator", "scripts", "context_builder_agent.py"
)
SYNTHESIZER = os.path.join(
    REPO_ROOT, "skills", "workflow-orchestrator", "scripts", "log_synthesizer_agent.py"
)

# Make log_filter and template_runner importable from the repo in dev mode.
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "android-log-analysis", "scripts"))
sys.path.insert(0, os.path.join(REPO_ROOT, "skills", "template-engine", "scripts"))

RG_AVAILABLE = shutil.which("rg") is not None


# ── Layer 1: log_filter unit tests ────────────────────────────────────────────

@unittest.skipUnless(RG_AVAILABLE, "ripgrep (rg) not installed — skipping log_filter tests")
class TestLogFilter(unittest.TestCase):
    """Direct tests of log_filter.filter_file() against the logcat fixture."""

    @classmethod
    def setUpClass(cls):
        from log_filter import filter_file, check_dependencies
        cls.filter_file = staticmethod(filter_file)
        check_dependencies()

    def test_wakelock_acquire_release_leak(self):
        result = self.filter_file(
            LOGCAT_FIXTURE,
            r"WakeLock.*(acquire|release|LEAK)",
            pattern_id="wakelock_lifecycle",
        )
        self.assertIsNone(result.error)
        self.assertGreater(result.match_count, 0)
        self.assertIn("WakeLock", result.lines)

    def test_wakelock_timeout(self):
        result = self.filter_file(
            LOGCAT_FIXTURE, r"WakeLock.*timeout", pattern_id="wakelock_timeout"
        )
        self.assertIsNone(result.error)
        self.assertGreater(result.match_count, 0)

    def test_wakelock_held_ms(self):
        result = self.filter_file(
            LOGCAT_FIXTURE, r"WakeLock.*held.*ms", pattern_id="wakelock_held"
        )
        self.assertIsNone(result.error)
        self.assertGreater(result.match_count, 0)

    def test_battery_stats(self):
        result = self.filter_file(
            LOGCAT_FIXTURE,
            r"BatteryStats.*(discharge|drain|level|charging|plugged)",
            pattern_id="battery_stats",
        )
        self.assertIsNone(result.error)
        self.assertGreater(result.match_count, 0)

    def test_power_manager_state(self):
        result = self.filter_file(
            LOGCAT_FIXTURE,
            r"PowerManager.*(suspend|wakeup|screen|goToSleep|wakeUp)",
            pattern_id="power_manager_state",
        )
        self.assertIsNone(result.error)
        self.assertGreater(result.match_count, 0)

    def test_doze_mode(self):
        result = self.filter_file(
            LOGCAT_FIXTURE,
            r"(DeviceIdleController|Doze).*(enter|exit|idle|light)",
            pattern_id="doze_mode",
        )
        self.assertIsNone(result.error)
        self.assertGreater(result.match_count, 0)

    def test_high_drain_inline_pattern(self):
        result = self.filter_file(
            LOGCAT_FIXTURE,
            r"drain_rate.*[5-9][0-9]%|mDischargeCurrentLevel.*[5-9][0-9]",
            pattern_id="high_drain",
        )
        self.assertIsNone(result.error)
        self.assertGreater(result.match_count, 0)

    def test_thermal_event_inline_pattern(self):
        result = self.filter_file(
            LOGCAT_FIXTURE,
            r"thermal|temperature.*(hot|critical|shutdown|throttl)",
            pattern_id="thermal_event",
        )
        self.assertIsNone(result.error)
        self.assertGreater(result.match_count, 0)

    def test_no_false_positives(self):
        result = self.filter_file(
            LOGCAT_FIXTURE,
            r"THIS_PATTERN_XYZZY_SHOULD_NEVER_MATCH_EVER",
            pattern_id="no_match",
        )
        self.assertIsNone(result.error)
        self.assertEqual(result.match_count, 0)

    def test_result_shape(self):
        from log_filter import FilterResult
        result = self.filter_file(
            LOGCAT_FIXTURE, r"WakeLock", pattern_id="shape_test"
        )
        self.assertIsInstance(result, FilterResult)
        self.assertEqual(result.pattern_id, "shape_test")
        self.assertEqual(result.source_file, "logcat_sample.txt")
        self.assertIsInstance(result.match_count, int)
        self.assertIsInstance(result.capped, bool)
        self.assertIsInstance(result.lines, str)


# ── Layer 2: template_runner tests ────────────────────────────────────────────

@unittest.skipUnless(RG_AVAILABLE, "ripgrep (rg) not installed — skipping template_runner tests")
class TestTemplateRunner(unittest.TestCase):
    """Tests template_runner.run_template() with the library wakelock template."""

    @classmethod
    def setUpClass(cls):
        from template_runner import run_template
        cls.run_template = staticmethod(run_template)

    def test_wakelock_template_finds_all_patterns(self):
        sections = self.run_template(WAKELOCK_TEMPLATE, LOGCAT_FIXTURE)
        ids = {s["pattern_id"] for s in sections}
        self.assertIn("wakelock_lifecycle", ids)
        self.assertIn("wakelock_timeout", ids)
        self.assertIn("wakelock_held", ids)

    def test_wakelock_template_all_patterns_have_matches(self):
        sections = self.run_template(WAKELOCK_TEMPLATE, LOGCAT_FIXTURE)
        for s in sections:
            self.assertGreater(
                s["match_count"], 0,
                f"Pattern '{s['pattern_id']}' had zero matches in logcat fixture"
            )

    def test_section_shape(self):
        sections = self.run_template(WAKELOCK_TEMPLATE, LOGCAT_FIXTURE)
        self.assertGreater(len(sections), 0)
        required_keys = {"pattern_id", "source_file", "match_count", "capped",
                         "description", "filtered_lines", "summary_prompt", "error"}
        for s in sections:
            self.assertTrue(required_keys.issubset(s.keys()),
                            f"Section missing keys: {required_keys - s.keys()}")

    def test_no_match_file_returns_zero(self):
        """A fixture with no relevant lines should return zero matches for all patterns."""
        sections = self.run_template(WAKELOCK_TEMPLATE, BUGREPORT_FIXTURE)
        for s in sections:
            self.assertEqual(
                s["match_count"], 0,
                f"Expected no wakelock matches in bugreport fixture, "
                f"but pattern '{s['pattern_id']}' returned {s['match_count']}"
            )


# ── Layer 3: E2E pipeline tests ───────────────────────────────────────────────

@unittest.skipUnless(RG_AVAILABLE, "ripgrep (rg) not installed — skipping E2E tests")
class TestE2EPipeline(unittest.TestCase):
    """
    End-to-end test: runs context_builder_agent.py then log_synthesizer_agent.py
    as subprocesses against the fixtures directory.

    Both scripts use dev-mode fallbacks to find skill modules in the repo,
    so no `setup.py` deployment is required.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="cline_test_e2e_")
        cls.context_path = None
        cls.report_path = None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_1_context_builder_exits_zero(self):
        result = subprocess.run(
            [sys.executable, CONTEXT_BUILDER,
             "--workflow", BATTERY_WORKFLOW,
             "--input", FIXTURES_DIR],
            capture_output=True, text=True,
            cwd=self.tmp_dir,
        )
        self.assertEqual(
            result.returncode, 0,
            f"context_builder_agent.py exited {result.returncode}:\n{result.stderr}"
        )
        context_path = result.stdout.strip()
        # Script prints a relative path — resolve it against the subprocess cwd.
        if not os.path.isabs(context_path):
            context_path = os.path.join(self.tmp_dir, context_path)
        self.assertTrue(
            os.path.isfile(context_path),
            f"log-context.md not created at '{context_path}'"
        )
        TestE2EPipeline.context_path = context_path

    def test_2_context_contains_expected_pattern_ids(self):
        if not self.context_path:
            self.skipTest("context_path not available — test_1 may have failed")
        with open(self.context_path) as f:
            content = f.read()
        for pid in ["wakelock_lifecycle", "battery_stats", "modem_wakeup"]:
            self.assertIn(pid, content, f"Pattern id '{pid}' missing from context.txt")

    def test_3_synthesizer_produces_report(self):
        if not self.context_path:
            self.skipTest("context_path not available — test_1 may have failed")

        api_key = os.environ.get("LLM_API_KEY")
        env = os.environ.copy()
        if not api_key:
            env["LLM_BACKEND"] = "cline"

        result = subprocess.run(
            [sys.executable, SYNTHESIZER, "--context", self.context_path],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(
            result.returncode, 0,
            f"log_synthesizer_agent.py exited {result.returncode}:\n{result.stderr}"
        )
        report_path = result.stdout.strip()
        self.assertTrue(
            os.path.isfile(report_path),
            f"report.md not created at '{report_path}'"
        )
        TestE2EPipeline.report_path = report_path

    def test_4_report_content(self):
        if not self.report_path:
            self.skipTest("report_path not available — test_3 may have failed")
        with open(self.report_path) as f:
            report = f.read()

        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            # Cline backend: placeholder markers must be present (format: <!-- SUMMARY_PROMPT: <id> ... -->)
            self.assertIn(
                "<!-- SUMMARY_PROMPT:", report,
                "Expected Cline placeholder markers in report (cline backend)"
            )
        else:
            # Real LLM: report should contain substantive content
            self.assertGreater(len(report), 200, "Report looks too short for a real LLM response")

        # Either way, the report should reference at least one known pattern
        self.assertTrue(
            any(pid in report for pid in ["wakelock", "battery", "modem", "drain"]),
            "Report does not reference any expected pattern keywords"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
