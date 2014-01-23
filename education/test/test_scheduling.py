from unittest import TestCase
from education.scheduling import *
from datetime import date

class TestScheduling(TestCase):

    def test_finds_upcoming_date(self):
        today = date(2013, 12, 29)
        dates = [date(2013, 12, 26), date(2014, 1, 2), date(2014, 1, 9)]
        self.assertEquals(date(2014, 1, 2), upcoming(dates, get_day = lambda: today))

    def test_current_date_doesnt_count_as_upcoming(self):
        today = date(2013, 12, 26)
        dates = [date(2013, 12, 26), date(2014, 1, 2), date(2014, 1, 9)]
        self.assertEquals(date(2014, 1, 2), upcoming(dates, get_day = lambda: today))

    def test_finds_when_no_upcoming_date(self):
        today = date(2014, 1, 29)
        dates = [date(2013, 12, 26), date(2014, 1, 2), date(2014, 1, 9)]
        self.assertEquals(None, upcoming(dates, get_day = lambda: today))

    def test_finds_current_period(self):
        today = date(2013, 12, 29)
        dates = [date(2013, 12, 26), date(2014, 1, 2), date(2014, 1, 9)]
        self.assertEquals((date(2013, 12, 26),date(2014, 1, 1)), current_period(dates, get_day = lambda: today))

    def test_finds_current_period_with_open_end(self):
        today = date(2014, 1, 29)
        dates = [date(2013, 12, 26), date(2014, 1, 2), date(2014, 1, 9)]
        self.assertEquals((date(2013, 12, 26),None), current_period(dates, get_day = lambda: today))

    def test_finds_current_period_with_open_start(self):
        today = date(2013, 11, 29)
        dates = [date(2013, 12, 26), date(2014, 1, 2), date(2014, 1, 9)]
        self.assertEquals((None,date(2013, 12, 25)), current_period(dates, get_day = lambda: today))

    def test_finds_upcoming_date_and_time_for_specific_poll(self):
        roster = {'p6_girls': [date(2013, 8, 29), date(2013, 9, 4)],
                  'p3_girls': [date(2013, 3, 29), date(2013, 4, 4)]}

        today = date(2013, 3, 30)

        self.assertEquals(datetime(2013, 4, 4, 10, 0, 0), next_scheduled('p3_girls', roster = roster, get_day = lambda: today))

    def test_finds_when_no_upcoming_date_and_time_for_specific_poll(self):
        today = date(2013, 3, 30)
        self.assertEquals(None, next_scheduled('p3_girls', roster = {}, get_day = lambda: today))
