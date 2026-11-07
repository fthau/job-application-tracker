"""
Unit tests for the Job Match algorithm (no database needed).

Run with:  python -m unittest test_job_match.py -v
"""

import unittest

from app import calculate_match, parse_skills, rank_jobs


class ParseSkillsTests(unittest.TestCase):
    def test_splits_trims_and_dedupes(self):
        self.assertEqual(parse_skills(" Python, sql ,  SQL,, Flask "), ["Python", "sql", "Flask"])

    def test_accepts_list_and_collapses_spaces(self):
        self.assertEqual(parse_skills(["Power   BI", "power bi", ""]), ["Power BI"])

    def test_empty_input(self):
        self.assertEqual(parse_skills(""), [])


class CalculateMatchTests(unittest.TestCase):
    def test_full_match(self):
        m = calculate_match(["Python", "SQL", "Flask"], ["Python", "SQL", "Flask"])
        assert m is not None
        self.assertEqual(m["percent"], 100)
        self.assertEqual((m["matched_count"], m["required_count"]), (3, 3))
        self.assertEqual(m["missing"], [])

    def test_partial_match_matches_spec_example(self):
        # Spec: "Data Analyst at DataCo - 67% (2/3 skills) Missing: Tableau"
        m = calculate_match(["Python", "SQL", "Flask"], ["Python", "SQL", "Tableau"])
        assert m is not None
        self.assertEqual(m["percent"], 67)
        self.assertEqual(m["missing"], ["Tableau"])

    def test_case_insensitive(self):
        m = calculate_match(["python", "MYSQL"], ["Python", "MySQL"])
        assert m is not None
        self.assertEqual(m["percent"], 100)

    def test_no_requirements_returns_none(self):
        self.assertIsNone(calculate_match(["Python"], []))
        self.assertIsNone(calculate_match(["Python"], None))

    def test_rounds_half_up(self):
        # 1 of 8 = 12.5% -> 13%
        m = calculate_match(["a"], list("abcdefgh"))
        assert m is not None
        self.assertEqual(m["percent"], 13)


class RankJobsTests(unittest.TestCase):
    JOBS = [
        {"job_id": 1, "job_title": "Data Analyst", "requirements": ["Python", "SQL", "Tableau"]},
        {"job_id": 2, "job_title": "Software Developer", "requirements": ["Python", "SQL", "Flask"]},
        {"job_id": 3, "job_title": "Designer", "requirements": ["Figma"]},
        {"job_id": 4, "job_title": "No Reqs", "requirements": []},
    ]

    def test_sorted_best_first_and_zero_hidden(self):
        results = rank_jobs(["Python", "SQL", "Flask"], self.JOBS)
        self.assertEqual([r["job_id"] for r in results], [2, 1])

    def test_include_zero(self):
        results = rank_jobs(["Python"], self.JOBS, include_zero=True)
        self.assertEqual(results[-1]["job_id"], 3)
        self.assertEqual(results[-1]["percent"], 0)


if __name__ == "__main__":
    unittest.main()
