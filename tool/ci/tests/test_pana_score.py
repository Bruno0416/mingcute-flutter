"""The pana gate accepts exactly 160/160 and nothing else."""
import json
import unittest

from _helpers import ROOT  # noqa: F401  (adds tool/ci to sys.path)
import check_pana_score as gate


def report(granted, maximum=160, sections=()):
    return json.dumps({'scores': {'grantedPoints': granted, 'maxPoints': maximum},
                       'report': {'sections': list(sections)}})


class PanaScoreTest(unittest.TestCase):
    def test_full_score_passes(self):
        self.assertEqual('160/160', gate.check(report(160)))

    def test_one_missing_point_blocks(self):
        for granted in (159, 150, 0):
            with self.subTest(granted=granted), self.assertRaisesRegex(ValueError, 'below 160/160'):
                gate.check(report(granted))

    def test_lost_sections_are_listed(self):
        sections = [{'title': 'Docs', 'grantedPoints': 10, 'maxPoints': 20}]
        with self.assertRaisesRegex(ValueError, 'Docs: 10/20'):
            gate.check(report(150, sections=sections))

    def test_changed_maximum_stops_instead_of_lowering_the_bar(self):
        with self.assertRaisesRegex(ValueError, 'model changed'):
            gate.check(report(170, 170))
        with self.assertRaisesRegex(ValueError, 'model changed'):
            gate.check(report(150, 150))

    def test_missing_empty_or_incomplete_output_blocks(self):
        for text in ('', '   ', 'pana crashed', '{}', '{"scores": {}}', '{"scores": {"grantedPoints": 160}}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                gate.check(text)

    def test_log_noise_before_json_is_tolerated_but_exit_codes_are_clear(self):
        self.assertEqual('160/160', gate.check('INFO noise\n' + report(160)))
        self.assertEqual(2, gate.main(['x']))
        self.assertEqual(1, gate.main(['x', '/nonexistent/pana.json']))


if __name__ == '__main__':
    unittest.main()
