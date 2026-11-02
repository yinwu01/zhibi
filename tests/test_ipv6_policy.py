import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from zhibi.ipv6_policy import confirm_run, policy_row, validate_confirmation
from zhibi.models import InputError, IPV6_ENDPOINT, now, timestamp
from zhibi.scan import scan_summary, validate_scan
from zhibi.scan_demo import run_demo


class IPv6PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.run = Path(run_demo('conflicting-sources', str(self.base / 'scan'))['directory'])
        self.evidence = self.base / 'scoped-config.txt'
        self.evidence.write_text('SYNTHETIC: dedicated environment IPv6 outbound blocked\n')
        self.report = json.loads((self.run / 'report.json').read_text())

    def confirm(self, **kwargs):
        return confirm_run(self.run, self.evidence, 'blocked', 'local_config', out=self.base / 'confirmed', **kwargs)

    def test_missing_evidence_is_actionable_never_a_pass(self):
        row = policy_row(self.report)
        self.assertEqual(row['state'], 'attention')
        self.assertEqual(row['result'], '待确认')
        self.assertIn('专用环境', row['advice'])
        self.assertIn('禁用 IPv6 出站', row['advice'])

    def test_review_record_is_bound_and_private(self):
        original = (self.run / 'report.json').read_bytes()
        result = self.confirm(reviewed=True)
        saved = json.loads((Path(result['directory']) / 'report.json').read_text())
        validate_scan(saved)
        self.assertEqual(policy_row(saved)['result'], '通过')
        self.assertEqual((self.run / 'report.json').read_bytes(), original)
        exported = json.dumps(result['summary'])
        self.assertNotIn(str(self.evidence), exported)
        self.assertNotIn('SYNTHETIC: dedicated', exported)
        self.assertTrue((Path(result['directory']) / 'ipv6-evidence.private.json').exists())
        for change in ('target', 'scope', 'scan'):
            altered = copy.deepcopy(saved)
            if change == 'scan':
                altered['generated_at'] = (timestamp(altered['generated_at']) + timedelta(seconds=1)).isoformat()
            else:
                altered['ipv6_confirmation'][change] = 'different'
            with self.assertRaises(InputError):
                validate_confirmation(altered)

    def test_confirmation_needs_review_and_current_scan(self):
        with self.assertRaises(InputError):
            self.confirm()
        old = (timestamp(now()) - timedelta(hours=1)).isoformat()
        self.report['generated_at'] = old
        (self.run / 'report.json').write_text(json.dumps(self.report))
        with self.assertRaises(InputError):
            self.confirm(reviewed=True)
        self.assertFalse((self.base / 'confirmed').exists())

    def test_live_ipv6_cannot_be_confirmed_closed(self):
        self.report['subjects'].append({'id':'agent-ipv6', 'family':6, 'measured_at':now(), 'endpoint':IPV6_ENDPOINT})
        (self.run / 'report.json').write_text(json.dumps(self.report))
        self.assertEqual(policy_row(self.report)['result'], '建议关闭')
        with self.assertRaises(InputError):
            self.confirm(reviewed=True)

    def test_failed_browser_request_is_not_disable_evidence(self):
        from test_assessment import AssessmentTests
        helper = AssessmentTests()
        helper.report = self.report
        self.report['paths'] = helper.paths()
        row = policy_row(self.report)
        self.assertEqual(row['result'], '待确认')
        self.assertNotEqual(row['state'], 'measured')


if __name__ == '__main__':
    unittest.main()
