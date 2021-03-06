from unittest import TestCase
from education.results import NumericResponsesFor
from education.test.utils import create_attribute
from education.models import *
from rapidsms.models import *
from eav.models import *
from datetime import datetime, timedelta

now = datetime(2013, 9, 12)

class TestResults(TestCase):

    def setUp(self):
        self.attribute = create_attribute()
        user = User.objects.create(username="peter")
        backend = Backend.objects.create()
        self.contact = EmisReporter.objects.create()
        self.poll = Poll.objects.create(name="foo", user=user, response_type=Poll.TYPE_NUMERIC)
        self.connection = Connection.objects.create(contact=self.contact, backend=backend)

        self.gulu = Location.objects.create(name="Gulu")
        self.kampala = Location.objects.create(name="Kampala")


    def reporter_for(self, location):
        return EmisReporter.objects.create(reporting_location=location)


    def record_response(self, text, value_float, direction='I', has_errors=False, date=now):
        message = Message.objects.create(direction=direction, text=text, connection=self.connection)
        response = Response.objects.create(contact=self.contact,
                                           poll=self.poll,
                                           message=message,
                                           has_errors=has_errors)
        response.date = date # auto_now_add doesn't let us set date on creation.
        response.save()
        value = Value.objects.create(attribute=self.attribute, entity=response, value_float=value_float)
        return response


    def record_response_for(self, contact, text, value_float):
        response = self.record_response(text, value_float)
        response.contact = contact
        response.save()
        return response


    def test_gathers_only_incoming_messages(self):
        self.record_response("8 boys", 8, direction='I')
        self.record_response("Do you have more than 1 latrine?", None, direction='O')
        self.assertEqual(1, NumericResponsesFor([self.poll]).query.count())
        self.assertEqual(8, NumericResponsesFor([self.poll]).total())


    def test_calculates_mode(self):
        self.record_response("8 boys", 8)
        self.record_response("9 boys", 9)
        self.record_response("9 boys", 9)
        self.record_response("10 boys", 10)
        self.record_response("10 boys", 10)
        self.record_response("10 boys", 10)
        self.assertEqual(10, NumericResponsesFor([self.poll]).mode())


    def test_gathers_only_error_free_messages(self):
        self.record_response("8 boys", 8, has_errors=False)
        self.record_response("My phone number is 0794443337", 794443337, has_errors=True)
        self.assertEqual(1, NumericResponsesFor([self.poll]).query.count())
        self.assertEqual(8, NumericResponsesFor([self.poll]).total())


    def test_calculates_mean(self):
        self.record_response("6 boys", 6)
        self.record_response("10 boys", 10)
        self.assertEqual(8, NumericResponsesFor([self.poll]).mean())


    def test_excludes_zeros(self):
        self.record_response("0 boys", 0)
        self.record_response("10 boys", 10)
        self.assertEqual(1, NumericResponsesFor([self.poll]).excludeZeros().query.count())


    def test_excludes_greater_than(self):
        self.record_response("6 boys", 6)
        self.record_response("10 boys", 10)
        self.assertEqual(6, NumericResponsesFor([self.poll]).excludeGreaterThan(6).total())


    def test_filters_by_date_range(self):
        today = now
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        next_week = today + timedelta(days=7)

        self.record_response("6 boys", 6, date=yesterday)
        self.record_response("10 boys", 10, date=tomorrow)

        self.assertEqual(10, NumericResponsesFor([self.poll]).forDateRange((today,next_week)).total())


    def test_filters_by_location(self):
        self.record_response_for(self.reporter_for(self.kampala), "6 boys", 6)
        self.record_response_for(self.reporter_for(self.gulu), "9 boys", 9)
        self.assertEqual(9, NumericResponsesFor([self.poll]).forLocations([self.gulu]).total())


    def test_filters_by_value(self):
        self.record_response_for(self.reporter_for(self.kampala), "6 boys", 6)
        self.record_response_for(self.reporter_for(self.kampala), "6 boys", 6)
        self.record_response_for(self.reporter_for(self.kampala), "7 boys", 7)
        self.record_response_for(self.reporter_for(self.gulu), "9 boys", 9)
        self.assertEqual(19, NumericResponsesFor([self.poll]).forValues([6, 7]).total())


    def test_mode_defaults_to_zero(self):
        self.assertEqual(0, NumericResponsesFor([self.poll]).mode())


    def test_groups_by_location(self):
        self.record_response_for(self.reporter_for(self.kampala), "6 boys", 6)
        self.record_response_for(self.reporter_for(self.kampala), "7 boys", 7)
        self.record_response_for(self.reporter_for(self.gulu), "9 boys", 9)
        results = NumericResponsesFor([self.poll]).groupByLocation()
        self.assertEqual(13, results[self.kampala.id])
        self.assertEqual(9, results[self.gulu.id])


    def test_filters_by_school(self):
        (mary, st_marys) = self.create_teacher_with_school()
        (mark, st_marks) = self.create_teacher_with_school()

        self.record_response_for(mary, "3 girls", 3)
        self.record_response_for(mark, "2 boys", 2)
        self.assertEqual(3, NumericResponsesFor([self.poll]).forSchools([st_marys]).total())


    def test_groups_by_school(self):
        (mary, st_marys) = self.create_teacher_with_school()
        (mark, st_marks) = self.create_teacher_with_school()

        self.record_response_for(mary, "3 girls", 3)
        self.record_response_for(mary, "4 girls", 4)
        self.record_response_for(mark, "2 boys", 2)
        results = NumericResponsesFor([self.poll]).groupBySchools()

        self.assertEqual(7, results[st_marys.id])
        self.assertEqual(2, results[st_marks.id])

    def create_teacher_with_school(self):
        teacher = EmisReporter.objects.create()
        school = School.objects.create(name="Foo", location=self.gulu)
        teacher.schools = [school]
        teacher.save()

        return (teacher, school)

    def tearDown(self):
        User.objects.all().delete()
        Backend.objects.all().delete()
        Contact.objects.all().delete()
        Poll.objects.all().delete()
        Message.objects.all().delete()
        Response.objects.all().delete()
        Value.objects.all().delete()
