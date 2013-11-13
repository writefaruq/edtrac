# vim: ai ts=4 sts=4 et sw=4 encoding=utf-8
from datetime import datetime
from unittest import TestCase
import dateutils
from django.conf import settings
from education.reports import is_holiday
from education.utils import get_week_count, get_months


class TestUtilFunctions(TestCase):
    def test_should_return_week_count_between_two_dates(self):
        start_date = datetime(2012,1,1)
        four_weeks_before = dateutils.increment(start_date, weeks=-4)
        self.assertEqual(5, get_week_count(four_weeks_before, start_date))

    def test_should_return_week_count_between_two_dates_passed_in_any_order(self):
        start_date = datetime(2012, 1, 1)
        four_weeks_before = dateutils.increment(start_date, weeks=-4)
        self.assertEqual(5, get_week_count(start_date, four_weeks_before))

    def test_should_give_proper_month_data_starting_from_today(self):
        start_date = datetime(2012, 1, 1)
        end_date = dateutils.increment(start_date, weeks=10)

        months = get_months(start_date, end_date)
        self.assertEqual(months[0][0].date(), start_date.date())
        self.assertEqual(months[-1][1].date(), end_date.date())

    def test_should_return_true_if_given_date_is_holiday(self):
        holiday_date = datetime(2012, 1, 1)
        settings.SCHOOL_HOLIDAYS = [(holiday_date, '1d')]
        self.assertTrue(is_holiday(holiday_date,getattr(settings,'SCHOOL_HOLIDAYS')))

    def test_should_return_false_if_given_date_is_not_holiday(self):
        holiday_date = datetime(2012, 1, 1)
        not_holiday_date = datetime(2012, 2, 1)

        settings.SCHOOL_HOLIDAYS = [(holiday_date,'1d')]
        self.assertFalse(is_holiday(not_holiday_date,getattr(settings,'SCHOOL_HOLIDAYS')))