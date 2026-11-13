from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lastfree.clock import last_free_day, run_clock
from lastfree.model import Job

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def job(**kwargs) -> Job:
    payload = {
        "container": "MSCU1234567",
        "preset": "uswc_port",
        "size": "40",
        "available_on": "2026-11-10",
        "as_of": "2026-11-12",
    }
    payload.update(kwargs)
    return Job.from_dict(payload)


class ClockTests(unittest.TestCase):
    def test_business_free_time_counts_weekdays(self) -> None:
        lfd = last_free_day(date(2026, 11, 10), 4, "business", set())
        self.assertEqual(lfd, date(2026, 11, 13))

    def test_business_free_time_skips_weekend(self) -> None:
        lfd = last_free_day(date(2026, 11, 13), 4, "business", set())
        self.assertEqual(lfd, date(2026, 11, 18))

    def test_business_free_time_skips_holiday(self) -> None:
        lfd = last_free_day(date(2026, 11, 10), 4, "business", {date(2026, 11, 11)})
        self.assertEqual(lfd, date(2026, 11, 16))

    def test_calendar_free_time_includes_weekend(self) -> None:
        lfd = last_free_day(date(2026, 11, 13), 4, "calendar", set())
        self.assertEqual(lfd, date(2026, 11, 16))

    def test_still_inside_before_lfd_is_free(self) -> None:
        result = run_clock(job())
        self.assertEqual(result.demurrage_lfd, date(2026, 11, 13))
        self.assertEqual(result.demurrage_usd, 0)
        self.assertEqual(result.projected_usd, 0)
        self.assertEqual(result.status, "inside_free")
        self.assertEqual(result.days_until_lfd, 1)

    def test_pickup_on_lfd_is_free(self) -> None:
        result = run_clock(job(gate_out_on="2026-11-13", as_of="2026-11-13"))
        self.assertEqual(result.demurrage_usd, 0)
        self.assertEqual(result.detention_lfd, date(2026, 11, 16))
        self.assertEqual(result.status, "on_street_free")

    def test_demurrage_starts_the_day_after_lfd(self) -> None:
        result = run_clock(job(gate_out_on="2026-11-16", as_of="2026-11-16"))
        self.assertEqual(result.demurrage_days, 1)
        self.assertEqual(result.demurrage_usd, 285.0)
        monday = next(cell for cell in result.calendar if cell.date == date(2026, 11, 16))
        self.assertEqual(monday.demurrage_usd, 285.0)
        self.assertIn("gate_out", monday.flags)

    def test_weekend_holiday_example_matches_readme(self) -> None:
        payload = json.loads((EXAMPLES / "weekend-holiday.json").read_text())
        result = run_clock(Job.from_dict(payload))
        self.assertEqual(result.demurrage_lfd, date(2026, 11, 16))
        self.assertEqual(result.detention_lfd, date(2026, 11, 22))
        self.assertEqual(result.demurrage_days, 3)
        self.assertEqual(result.detention_days, 3)
        self.assertEqual(result.demurrage_usd, 855.0)
        self.assertEqual(result.detention_usd, 480.0)
        self.assertEqual(result.projected_usd, 1335.0)
        self.assertEqual(result.status, "closed")

    def test_gated_with_fees_example(self) -> None:
        payload = json.loads((EXAMPLES / "gated-with-fees.json").read_text())
        result = run_clock(Job.from_dict(payload))
        self.assertEqual(result.demurrage_lfd, date(2026, 11, 6))
        self.assertEqual(result.detention_lfd, date(2026, 11, 16))
        self.assertEqual(result.demurrage_days, 4)
        self.assertEqual(result.detention_days, 4)
        self.assertEqual(result.demurrage_usd, 780.0)
        self.assertEqual(result.detention_usd, 780.0)
        self.assertEqual(result.projected_usd, 1560.0)

    def test_twenty_foot_uses_size_factor(self) -> None:
        payload = json.loads((EXAMPLES / "gated-with-fees.json").read_text())
        payload["size"] = "20"
        result = run_clock(Job.from_dict(payload))
        self.assertEqual(result.demurrage_usd, 624.0)
        self.assertEqual(result.detention_usd, 624.0)

    def test_tier_steps_up_after_five_uswc_days(self) -> None:
        result = run_clock(
            job(
                available_on="2026-11-02",
                gate_out_on="2026-11-13",
                as_of="2026-11-13",
                holidays=[],
            )
        )
        # LFD = Wed 5 Nov (4 business from Mon 2). Charge through Fri 13:
        # 6, 9, 10, 11, 12, 13 = 6 business days → 5*285 + 400
        self.assertEqual(result.demurrage_lfd, date(2026, 11, 5))
        self.assertEqual(result.demurrage_days, 6)
        self.assertEqual(result.demurrage_usd, 5 * 285 + 400)

    def test_accrued_stops_at_as_of_when_return_is_later(self) -> None:
        result = run_clock(
            job(
                preset="line_calendar",
                available_on="2026-11-01",
                gate_out_on="2026-11-10",
                empty_return_on="2026-11-25",
                as_of="2026-11-20",
            )
        )
        self.assertLess(result.accrued_usd, result.projected_usd)
        self.assertEqual(result.detention_lfd, date(2026, 11, 16))
        self.assertEqual(result.status, "detention_running")

    def test_duplicate_sku_style_container_is_normalized(self) -> None:
        result = run_clock(job(container="mscu-1234567"))
        self.assertEqual(result.job.container, "MSCU1234567")

    def test_empty_return_without_gate_out_is_invalid(self) -> None:
        with self.assertRaises(ValueError):
            job(empty_return_on="2026-11-20")

    def test_gate_out_before_available_is_invalid(self) -> None:
        with self.assertRaises(ValueError):
            job(gate_out_on="2026-11-01")
