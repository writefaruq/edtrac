"""
Basic tests for Edtrac
"""
from django.test import TestCase
from rapidsms.messages.incoming import IncomingMessage, OutgoingMessage
from rapidsms_xforms.models import *
from rapidsms_httprouter.models import Message
from rapidsms.contrib.locations.models import Location, LocationType
import datetime
from rapidsms.models import Connection, Backend, Contact
from rapidsms_xforms.models import XForm, XFormSubmission
from django.conf import settings
from script.utils.outgoing import check_progress
from script.models import Script, ScriptProgress, ScriptSession, ScriptResponse, ScriptStep
from education.management import *
from rapidsms_httprouter.router import get_router
from script.signals import script_progress_was_completed, script_progress
from poll.management import create_attributes
from education.models import EmisReporter, School, reschedule_weekly_polls, reschedule_monthly_polls, reschedule_termly_polls
from django.db import connection
from script.utils.outgoing import check_progress
from django.core.management import call_command
from unregister.models import Blacklist
from education.utils import _next_thursday, _date_of_monthday, _next_midterm, _next_term_question_date
from poll.models import ResponseCategory
import difflib

class ModelTest(TestCase): #pragma: no cover
    # Model tests
    def setUp(self):
        if 'django.contrib.sites' in settings.INSTALLED_APPS:
            site_id = getattr(settings, 'SITE_ID', 5)
            Site.objects.get_or_create(pk=site_id, defaults={'domain':'rapidemis.com'})
            fixtures = ['initial_data.json']
        User.objects.get_or_create(username='admin')
        self.backend = Backend.objects.create(name='test')
        self.connection = Connection.objects.create(identity='8675309', backend=self.backend)
        country = LocationType.objects.create(name='country', slug='country')
        district = LocationType.objects.create(name='district', slug='district')
        subcounty = LocationType.objects.create(name='sub_county', slug='sub_county')
        self.root_node = Location.objects.create(type=country, name='Uganda')
        self.kampala_district = Location.objects.create(type=district, name='Kampala')
        self.kampala_subcounty = Location.objects.create(type=subcounty, name='Kampala')
        self.gulu_subcounty = Location.objects.create(type=subcounty, name='Gulu')
        self.gulu_school = School.objects.create(name="St. Mary's", location=self.gulu_subcounty)
        self.kampala_school = School.objects.create(name="St. Mary's", location=self.kampala_subcounty)
        self.kampala_school2 = School.objects.create(name="St. Peters", location=self.kampala_district)
        self.kampala_school3 = School.objects.create(name="St. Mary's", location=self.kampala_district)

    def fake_incoming(self, message, connection=None):
        if connection is None:
            connection = self.connection
        router = get_router()
        return router.handle_incoming(connection.backend.name, connection.identity, message)
#        form = XForm.find_form(message)
#        incoming_message = IncomingMessage(connection, message)
#        incoming_message.db_message = Message.objects.create(direction="I", connection=connection, text=message)
#        if form:
#            submission = form.process_smc_submission(
#
#            )
#            return XFormSubmission.objects.all().order_by('-created')[0]


    def spoof_incoming_obj(self, message, connection=None):
        if connection is None:
            connection = Connection.objects.all()[0]
        incomingmessage = IncomingMessage(connection, message)
        incomingmessage.db_message = Message.objects.create(direction='I', connection=Connection.objects.all()[0], text=message)
        return incomingmessage


    def assertResponseEquals(self, message, expected_response, connection=None):
        s = self.fake_incoming(message, connection)
        self.assertEquals(s.response, expected_response)


    def fake_submission(self, message, connection=None):
        form = XForm.find_form(message)
        if connection is None:
            try:
                connection = Connection.objects.all()[0]
            except IndexError:
                backend, created = Backend.objects.get_or_create(name='test')
                connection, created = Connection.objects.get_or_create(identity='8675309',
                    backend=backend)
            # if so, process it
        incomingmessage = IncomingMessage(connection, message)
        incomingmessage.db_message = Message.objects.create(direction='I', connection=connection, text=message)
        if form:
            submission = form.process_sms_submission(incomingmessage)
            return submission
        return None


    def fake_error_submission(self, message, connection=None):
        form = XForm.find_form(message)

        if connection is None:
            connection = Connection.objects.all()[0]
            # if so, process it
        incomingmessage = IncomingMessage(connection, message)
        incomingmessage.db_message = Message.objects.create(direction='I', connection=Connection.objects.all()[0], text=message)
        if form:
            submission = form.process_sms_submission(incomingmessage)
            self.failUnless(submission.has_errors)
        return

    def elapseTime(self, submission, seconds):
        newtime = submission.created - datetime.timedelta(seconds=seconds)
        cursor = connection.cursor()
        cursor.execute("update rapidsms_xforms_xformsubmission set created = '%s' where id = %d" %
                       (newtime.strftime('%Y-%m-%d %H:%M:%S.%f'), submission.pk))


    def total_seconds(self, time_delta):
        """
        function to return total seconds in interval (for Python less than 2.7)
        """
        seconds = time_delta.seconds
        days_to_seconds = time_delta.days * 24 * 60 * 60
        return seconds + days_to_seconds


    def elapseTime2(self, progress, seconds):
        """
        This hack mimics the progression of time, from the perspective of a linear test case,
        by actually *subtracting* from the value that's currently stored (usually datetime.datetime.now())
        """
        progress.set_time(progress.time - datetime.timedelta(seconds=seconds))
        try:
            session = ScriptSession.objects.get(connection=progress.connection, script__slug=progress.script.slug, end_time=None)
            session.start_time = session.start_time - datetime.timedelta(seconds=seconds)
            session.save()
        except ScriptSession.DoesNotExist:
            pass

    def fake_script_dialog(self, script_prog, connection, responses, emit_signal=True):
        script = script_prog.script
        ss = ScriptSession.objects.create(script=script, connection=connection, start_time=datetime.datetime.now())
        for poll_name, resp in responses:
            poll = script.steps.get(poll__name=poll_name).poll
            poll.process_response(self.spoof_incoming_obj(resp, connection))
            resp = poll.responses.all()[0]
            ScriptResponse.objects.create(session=ss, response=resp)
        if emit_signal:
            script_progress_was_completed.send(connection=connection, sender=script_prog)
        return ss

    def register_reporter(self, grp, phone=None):
        connection = Connection.objects.create(identity=phone, backend=self.backend) if phone else self.connection
        self.fake_incoming('join', connection)
        script_prog = ScriptProgress.objects.filter(script__slug='edtrac_autoreg').order_by('-time')[0]

        params = [
            ('edtrac_role', grp, ['all']),\
            ('edtrac_gender', 'male', ['Head Teachers']),\
            ('edtrac_class', 'p3', ['Teachers']),\
            ('edtrac_district', 'kampala', ['all']),\
            ('edtrac_subcounty', 'kampala', ['all']),\
            ('edtrac_school', 'st. marys', ['Teachers', 'Head Teachers', 'SMC']),\
            ('edtrac_name', 'testy mctesterton', ['all']),\
        ]
        param_list = []
        for step_name, value, grps in params:
            g = difflib.get_close_matches(grp, grps, 1, 0.8)
            if grps[0] == 'all':
                param_list.append((step_name, value))
            elif len(g)>0:
                param_list.append((step_name, value))
            else:
                pass
        self.fake_script_dialog(script_prog, connection, param_list)

    def ask_for_data(self, connection = None, script_slug = None):
        """
        This function is used to ask for data or a response to polls that weren't answered. It can be turned on like
        a switch.
        """
        if (connection is not None) and (script_slug is not None):
            # get existing script with script slug
            script = Script.objects.get(slug = script_slug)
            # setup script
            # create a random ScriptProgress to mimic much of the existing ScriptProgress
            ScriptProgress.objects.create(
                connection = connection,
                script = script
            )

    def testBasicAutoReg(self):
        Script.objects.filter(slug='edtrac_autoreg').update(enabled=True)
        self.register_reporter('teacher')
        self.assertEquals(EmisReporter.objects.count(), 1)
        contact = EmisReporter.objects.all()[0]
        self.assertEquals(contact.name, 'Testy Mctesterton')
        self.assertEquals(contact.reporting_location, self.kampala_subcounty)
        self.assertEquals(contact.schools.all()[0], self.kampala_school)
        self.assertEquals(contact.groups.all()[0].name, 'Teachers')
        self.assertEquals(contact.grade, 'P3')
        self.assertEquals(contact.gender, None)
        self.assertEquals(contact.default_connection, self.connection)
        self.assertEquals(ScriptProgress.objects.filter(connection=self.connection).count(), 2)
        self.assertListEqual(list(ScriptProgress.objects.filter(connection=self.connection).values_list('script__slug', flat=True)), ['edtrac_autoreg', 'edtrac_teachers_weekly'])

    def testBadAutoReg(self):
        """
        Crummy answers
        """
        self.fake_incoming('join')
        script_prog = ScriptProgress.objects.all()[0]
        self.fake_script_dialog(script_prog, self.connection, [\
            ('edtrac_role', 'bodaboda'),\
            ('edtrac_district', 'kampala'),\
            ('edtrac_subcounty', 'amudat'),\
            ('edtrac_name', 'bad tester'),\
        ])
        self.assertEquals(EmisReporter.objects.count(), 1)
        contact = EmisReporter.objects.all()[0]
        self.assertEquals(contact.groups.all()[0].name, 'Other Reporters')
        self.assertEquals(contact.reporting_location, self.kampala_district)

    def testAutoRegNoLocationData(self):

        self.fake_incoming('join')
        script_prog = ScriptProgress.objects.all()[0]
        self.fake_script_dialog(script_prog, self.connection, [\
            ('edtrac_role', 'teacher'),\
            ('edtrac_name', 'no location data tester'),\
        ])
        self.assertEquals(EmisReporter.objects.count(), 1)
        contact = EmisReporter.objects.all()[0]
        self.assertEquals(contact.reporting_location, self.root_node)

    def testAutoRegNoRoleNoName(self):
        self.fake_incoming('join')
        script_prog = ScriptProgress.objects.all()[0]
        self.fake_script_dialog(script_prog, self.connection, [\
            ('edtrac_district', 'kampala'),\
            ('edtrac_subcounty', 'Gul'),\
            ('edtrac_school', 'St Marys'),\
        ])
        contact = EmisReporter.objects.all()[0]
        self.assertEquals(contact.groups.all()[0].name, 'Other Reporters')
        self.assertEquals(contact.reporting_location, self.gulu_subcounty)
        self.assertEquals(contact.name, 'Anonymous User')
        #without a role a reporter should not be scheduled for any regular polls
        self.assertListEqual(list(ScriptProgress.objects.filter(connection=self.connection).values_list('script__slug', flat=True)), ['edtrac_autoreg'])

    def testBasicQuit(self):
        self.register_reporter('teacher')
        ScriptProgress.objects.filter(script__slug='edtrac_autoreg', connection=self.connection).delete() #script always deletes a connection on completion of registration
        #quit system
        self.fake_incoming('quit')
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, "Thank you for your contribution to EduTrac. To rejoin the system, send join to 6200")
        self.assertEquals(Blacklist.objects.filter(connection=self.connection).count(), 1) #blacklisted
        self.assertEquals(EmisReporter.objects.count(), 1) #the user is not deleted, only blacklisted
    
    def testDoubleReg(self):
        
        #join again when already in the process of registration
        self.fake_incoming('join')
        self.fake_incoming('join')
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, "Your registration is not complete yet, you do not need to 'Join' again.")
        
        #cleanout scriptprogress and register again
        ScriptProgress.objects.filter(script__slug='edtrac_autoreg', connection=self.connection).delete()
        self.register_reporter('teacher')
        self.assertEquals(EmisReporter.objects.count(), 1)
        contact = EmisReporter.objects.all()[0]
        self.assertEquals(contact.name, 'Testy Mctesterton')
        self.assertEquals(contact.reporting_location, self.kampala_subcounty)
        self.assertEquals(contact.schools.all()[0], self.kampala_school)
        self.assertEquals(contact.groups.all()[0].name, 'Teachers')

        self.fake_incoming('join')
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, "You are already in the system and do not need to 'Join' again.")
        self.assertEquals(ScriptProgress.objects.filter(script__slug='edtrac_autoreg').count(), 1)

    def testQuitRejoin(self):
        #first join
        self.register_reporter('teacher')
        self.assertEquals(EmisReporter.objects.count(), 1)
        #when a user sucessfully registers, their registration is expunged from script progress
        ScriptProgress.objects.filter(script__slug='edtrac_autoreg', connection=self.connection).delete()

        #then quit
        self.fake_incoming('quit')
        self.assertEquals(Blacklist.objects.all()[0].connection, self.connection)
        self.assertEquals(EmisReporter.objects.all()[0].active, False)

        #rejoin
#        self.fake_incoming('join')
#        script_prog = ScriptProgress.objects.all()[0]

        self.register_reporter('teacher')
        self.assertEquals(EmisReporter.objects.count(), 1)
        
    def testQuitIncompleteRegistration(self):
        #first join
        self.fake_incoming('join')
        self.assertEquals(ScriptProgress.objects.filter(script__slug='edtrac_autoreg', connection=self.connection).count(), 1)

        #then quit
        self.fake_incoming('quit')
        self.assertEquals(Blacklist.objects.count(), 0)
        #notify user to first complete current registration
        self.assertEquals(Message.objects.all().order_by('-date')[0].text, 'Your registration is not complete, you can not quit at this point')
        #their current registration process is still valid
        self.assertEquals(ScriptProgress.objects.filter(script__slug='edtrac_autoreg', connection=self.connection).count(), 1)
        
    def testGemAutoReg(self):
        self.fake_incoming('join')
        self.assertEquals(ScriptProgress.objects.count(), 1)
        script_prog = ScriptProgress.objects.all()[0]
        self.assertEquals(script_prog.script.slug, 'edtrac_autoreg')

        self.fake_script_dialog(script_prog, self.connection, [\
            ('edtrac_role', 'gem'),\
            ('edtrac_district', 'kampala'),\
            ('edtrac_name', 'testy mctesterton'),\
        ])
        self.assertEquals(EmisReporter.objects.count(), 1)
        contact = EmisReporter.objects.all()[0]
        self.assertEquals(contact.name, 'Testy Mctesterton')
        self.assertEquals(contact.reporting_location, self.kampala_district)
        self.assertEquals(contact.groups.all()[0].name, 'GEM')
        self.assertEquals(ScriptProgress.objects.filter(connection=self.connection).count(), 2)
        self.assertListEqual(list(ScriptProgress.objects.filter(connection=self.connection).values_list('script__slug', flat=True)), ['edtrac_autoreg', 'edtrac_gem_monthly'])



    def testMeoAutoReg(self):
        self.fake_incoming('join')
        self.assertEquals(ScriptProgress.objects.count(), 1)
        script_prog = ScriptProgress.objects.all()[0]
        self.assertEquals(script_prog.script.slug, 'edtrac_autoreg')

        self.fake_script_dialog(script_prog, self.connection, [\
            ('edtrac_role', 'meo'),\
            ('edtrac_district', 'kampala'),\
            ('edtrac_name', 'testy mctesterton'),\
        ])
        self.assertEquals(EmisReporter.objects.count(), 1)
        contact = EmisReporter.objects.all()[0]
        self.assertEquals(contact.name, 'Testy Mctesterton')
        self.assertEquals(contact.reporting_location, self.kampala_district)
        self.assertEquals(contact.groups.all()[0].name, 'MEO')
        self.assertEquals(ScriptProgress.objects.filter(connection=self.connection).count(), 1)
        self.assertListEqual(list(ScriptProgress.objects.filter(connection=self.connection).values_list('script__slug', flat=True)), ['edtrac_autoreg'])


    def testTeacherAutoregProgression(self):
        Script.objects.filter(slug='edtrac_autoreg').update(enabled=True)
        self.fake_incoming('join')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        call_command('check_script_progress', e=8, l=24)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=0).poll.question)
        self.fake_incoming('Teacher')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        call_command('check_script_progress', e=8, l=24)
        self.assertNotEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=1).poll.question)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=2).poll.question)
        self.fake_incoming('P3')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        call_command('check_script_progress', e=8, l=24)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=3).poll.question)
        self.fake_incoming('Kampala')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        call_command('check_script_progress', e=8, l=24)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=4).poll.question)
        self.fake_incoming('Kampala')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        call_command('check_script_progress', e=8, l=24)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=5).poll.question)
        self.fake_incoming('St. Marys')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        call_command('check_script_progress', e=8, l=24)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=6).poll.question)
        self.fake_incoming('test mctester')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        call_command('check_script_progress', e=8, l=24)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=7).message)

    def testSMCAutoregProgression(self):
        Script.objects.filter(slug='edtrac_autoreg').update(enabled=True)
        self.fake_incoming('join')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=0).poll.question)
        self.fake_incoming('SMC')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=3).poll.question)
        self.fake_incoming('Kampala')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=4).poll.question)
        self.fake_incoming('Kampala')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=5).poll.question)
        self.fake_incoming('St. Marys')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=6).poll.question)
        self.fake_incoming('test mctester')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=7).message)

    def testGEMAutoregProgression(self):
        Script.objects.filter(slug='edtrac_autoreg').update(enabled=True)
        self.fake_incoming('join')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=0).poll.question)
        self.fake_incoming('GEM')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=3).poll.question)
        self.fake_incoming('Kampala')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=4).poll.question)
        self.fake_incoming('Kampala')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=6).poll.question)
        self.fake_incoming('test mctester')
        script_prog = ScriptProgress.objects.get(connection=self.connection, script__slug='edtrac_autoreg')
        self.elapseTime2(script_prog, 3601)
        check_progress(script_prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_autoreg').steps.get(order=7).message)


    def testWeeklyTeacherPolls(self):
        self.register_reporter('teacher')
        Script.objects.filter(slug__in=['edtrac_teachers_weekly', 'edtrac_teachers_monthly']).update(enabled=True)
        prog = ScriptProgress.objects.get(script__slug='edtrac_teachers_weekly', connection=self.connection)
        seconds_to_thursday = self.total_seconds(_next_thursday() - datetime.datetime.now())
        self.elapseTime2(prog, seconds_to_thursday+(1*60*60)) #seconds to thursday + one hour
        prog = ScriptProgress.objects.get(script__slug='edtrac_teachers_weekly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_teachers_weekly').steps.get(order=0).poll.question)
        self.fake_incoming('40')
        self.assertEquals(Message.objects.filter(direction='I').order_by('-date')[0].application, 'script')
        self.assertEquals(Script.objects.get(slug='edtrac_teachers_weekly').steps.get(order=0).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 40)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_teachers_weekly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_teachers_weekly').steps.get(order=2).poll.question)
        self.fake_incoming('55girls')
        self.fake_incoming('65girls') # proof that the last instantaneous response is not equal to 65
        self.assertEquals(Script.objects.get(slug='edtrac_teachers_weekly').steps.get(order=2).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 55)
        self.assertNotEquals(Script.objects.get(slug='edtrac_teachers_weekly').steps.get(order=2).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 65)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_teachers_weekly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_teachers_weekly').steps.get(order=4).poll.question)
        self.fake_incoming('3')
        self.assertEquals(Script.objects.get(slug='edtrac_teachers_weekly').steps.get(order=4).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 3)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_teachers_weekly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).__unicode__(), 'Not Started')
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.date(), _next_thursday().date())

    def testTermlyHeadTeacherSpecialPolls(self):
        self.testTermlyHeadTeacherPolls()

        #TODO add testing for special script poll

    def testAddCelery(self):
        from education.tasks import add
        res = add.delay(3, 4)
        self.assertEquals(res.get(), 7)

    def playTimeTrick(self, progress):
        time = progress.time
        now = datetime.datetime.now()
        return self.total_seconds(time - now)


    def testWeeklyHeadTeacherPolls(self):
        self.register_reporter('head teacher')
        Script.objects.filter(slug__in=['edtrac_head_teachers_weekly', 'edtrac_head_teachers_monthly', 'edtrac_head_teachers_termly']).update(enabled=True)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_weekly', connection=self.connection)
        seconds_to_thursday = self.total_seconds(_next_thursday() - datetime.datetime.now())
        self.elapseTime2(prog, seconds_to_thursday+(1*60*60)) #seconds to thursday + one hour
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_weekly', connection=self.connection)
        check_progress(prog.script); check_progress(prog.script); check_progress(prog.script); check_progress(prog.script); # multiple check_progresses for Head Teacher b'se of question skip
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_weekly').steps.get(order=0).poll.question)
        self.fake_incoming('6')
        self.assertEquals(Message.objects.filter(direction='I').order_by('-date')[0].application, 'script')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_weekly').steps.get(order=0).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 6)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_weekly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_weekly').steps.get(order=1).poll.question)
        self.fake_incoming('5 male teachers')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_weekly').steps.get(order=1).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 5)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_weekly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).__unicode__(), 'Not Started')
        #FIXTHIS -> the time for script progress has been back-tracked, need a way to compare the times in this dummy situation
#        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time,
#            _next_thursday(sp = ScriptProgress.objects.get(connection=self.connection, script=prog.script)))
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.year, _next_thursday().year)
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.day, _next_thursday().day)
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.month, _next_thursday().month)
        # seconds are a little unpredictable, sticking to the hour for time.
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.hour, _next_thursday().hour)
#        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.second, _next_thursday().second)


    def testMonthlyHeadTeacherPolls(self):
        self.register_reporter('head teacher')
        Script.objects.filter(slug__in=['edtrac_head_teachers_weekly', 'edtrac_head_teachers_monthly', 'edtrac_head_teachers_termly']).update(enabled=True)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_monthly', connection=self.connection)
        d = _date_of_monthday('last')
        seconds_to_lastday = self.total_seconds(d - datetime.datetime.now())
        self.elapseTime2(prog, seconds_to_lastday+(1*60*60)) #seconds to last day of month + one hour
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_monthly', connection=self.connection)
        self.assertEquals(prog.script.steps.count(), 2)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_monthly').steps.get(order=0).poll.question)
        self.fake_incoming('5')
        self.assertEquals(Message.objects.filter(direction='I').order_by('-date')[0].application, 'script')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_monthly').steps.get(order=0).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 5)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_monthly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_monthly').steps.get(order=1).poll.question)
        self.fake_incoming('25%')
        self.assertEquals(Message.objects.filter(direction='I').order_by('-date')[0].application, 'script')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_monthly').steps.get(order=1).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 25)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_monthly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).__unicode__(), 'Not Started')
        seconds_to_nextprog = self.total_seconds(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time - datetime.datetime.now())
        seconds_to_monthday = self.total_seconds(_date_of_monthday('last') - datetime.datetime.now())
        self.assertEquals(seconds_to_nextprog, seconds_to_monthday)


#    def testTermlySMCPolls(self):
#        self.register_reporter('SMC')
#        Script.objects.filter(slug='edtrac_smc_termly').update(enabled=True)
#        prog = ScriptProgress.objects.get(script__slug="edtrac_smc_termly", connection=self.connection)
#        d = _next_term_question_date()
#        seconds_to_midterm = self.total_seconds(d - datetime.datetime.now())
#        self.elapseTime2(prog, seconds_to_midterm+(1*60*60))
#        prog = ScriptProgress.objects.get(script__slug="edtrac_smc_termly", connection=self.connection)
#        check_progress(prog.script)
#        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text,\
#            Script.objects.get(slug="edtrac_smc_termly").steps.get(order=0).poll.question)
#        self.fake_incoming('yes')
#        self.assertEquals(Message.objects.filter(direction="I").order_by('-date')[0].application, 'script')


    def testTermlyHeadTeacherPolls(self):
        self.register_reporter('head teacher')
        Script.objects.filter(slug__in=['edtrac_head_teachers_weekly', 'edtrac_head_teachers_monthly', 'edtrac_head_teachers_termly']).update(enabled=True)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        d = _next_term_question_date()
        seconds_to_midterm = self.total_seconds(d - datetime.datetime.now())
        self.elapseTime2(prog, seconds_to_midterm+(1*60*60)) #seconds to 25th + one hour
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=0).poll.question)
        self.fake_incoming('85')
        self.assertEquals(Message.objects.filter(direction='I').order_by('-date')[0].application, 'script')
        print Message.objects.all()
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=0).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 85)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=1).poll.question)
        self.fake_incoming('25')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=1).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 25)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=2).poll.question)
        self.fake_incoming('25')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=2).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 25)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=3).poll.question)
        self.fake_incoming('25')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=3).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 25)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=4).poll.question)
        self.fake_incoming('25')
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=5).poll.question)
        self.fake_incoming('25')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=5).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 25)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=6).poll.question)
        self.fake_incoming('yes')
        self.assertEquals(Script.objects.get(slug='edtrac_head_teachers_termly').steps.get(order=6).poll.responses.all().order_by('-date')[0].eav.poll_text_value, 'yes')
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_head_teachers_termly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).__unicode__(), 'Not Started')
        #time checks
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.date(), d.date())
        # micro seconds make test fail
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.time().hour, d.time().hour)
#        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.time().minute, d.time().minute)

    def testWeeklySMCPolls(self):
        import ipdb; ipdb.set_trace()
        self.register_reporter('smc')
        Script.objects.filter(slug__in=['edtrac_smc_weekly', 'edtrac_smc_monthly', 'edtrac_smc_termly']).update(enabled=True)
        prog = ScriptProgress.objects.get(script__slug='edtrac_smc_weekly', connection=self.connection)
        seconds_to_thursday = self.total_seconds(_next_thursday() - datetime.datetime.now())
        self.elapseTime2(prog, seconds_to_thursday+(1*60*60)) #seconds to thursday + one hour
        prog = ScriptProgress.objects.get(script__slug='edtrac_smc_weekly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_smc_weekly').steps.get(order=0).poll.question)
        self.fake_incoming('yes')
        check_progress(prog.script)
        poll = Script.objects.get(slug='edtrac_smc_weekly').steps.get(order=0).poll
        yes_category = poll.categories.filter(name='yes')
        response = poll.responses.all().order_by('-date')[0]
        self.assertEquals(ResponseCategory.objects.get(response__poll__name=poll.name,  category=yes_category).response, response)
        prog = ScriptProgress.objects.get(script__slug='edtrac_smc_weekly', connection=self.connection)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_smc_weekly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).__unicode__(), 'Not Started')
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time.date(), _next_thursday(prog).date())

    def testMonthlySMCPolls(self):
        self.register_reporter('smc')
        Script.objects.filter(slug__in=['edtrac_smc_weekly', 'edtrac_smc_monthly', 'edtrac_smc_termly']).update(enabled=True)
        prog = ScriptProgress.objects.get(script__slug='edtrac_smc_monthly', connection=self.connection)
        d = _date_of_monthday(5)
        seconds_to_5th = self.total_seconds(d - datetime.datetime.now())
        self.elapseTime2(prog, seconds_to_5th+(1*60*60)) #seconds to 5th + one hour
        prog = ScriptProgress.objects.get(script__slug='edtrac_smc_monthly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(Message.objects.filter(direction='O').order_by('-date')[0].text, Script.objects.get(slug='edtrac_smc_monthly').steps.get(order=0).poll.question)
        self.fake_incoming('50%')
        self.assertEquals(Script.objects.get(slug='edtrac_smc_monthly').steps.get(order=0).poll.responses.all().order_by('-date')[0].eav.poll_number_value, 50)
        prog = ScriptProgress.objects.get(script__slug='edtrac_smc_monthly', connection=self.connection)
        self.elapseTime2(prog, 61)
        prog = ScriptProgress.objects.get(script__slug='edtrac_smc_monthly', connection=self.connection)
        check_progress(prog.script)
        self.assertEquals(ScriptProgress.objects.get(connection=self.connection, script=prog.script).__unicode__(), 'Not Started')
        seconds_to_nextprog = self.total_seconds(ScriptProgress.objects.get(connection=self.connection, script=prog.script).time - datetime.datetime.now())
        seconds_to_monthday = self.total_seconds(_date_of_monthday(5) - datetime.datetime.now())
        self.assertEquals(seconds_to_nextprog, seconds_to_monthday)

    def testRescheduleWeeklyPolls(self):
        ScriptProgress.objects.all().delete()
        self.register_reporter('teacher', '8675349')
        self.register_reporter('head teacher', '8675319')
        self.register_reporter('smc', '8675329')
        #GEM reporters only get Monthly questiosn asked
        #self.register_reporter('gem', '8675339')
        weekly_scripts = Script.objects.filter(slug__endswith='_weekly')
        Script.objects.filter(slug__in=weekly_scripts.values_list('slug', flat=True)).update(enabled=True)
        for sp in ScriptProgress.objects.filter(script__slug__in=weekly_scripts.values_list('slug', flat=True)):
            self.elapseTime2(sp, 13*31*24*60*60)
        self.assertEquals(ScriptProgress.objects.filter(script__slug__in=weekly_scripts.values_list('slug', flat=True))[0].time.year, datetime.datetime.now().year - 1)
        reschedule_weekly_polls('teachers')
        next_thursday = _next_thursday()
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675349', script__slug='edtrac_teachers_weekly').time.date(), next_thursday.date())
        reschedule_weekly_polls('head teachers')
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675319', script__slug='edtrac_head_teachers_weekly').time.date(), next_thursday.date())
        reschedule_weekly_polls('smc')
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675329', script__slug='edtrac_smc_weekly').time.date(), next_thursday.date())
        for sp in ScriptProgress.objects.filter(script__slug__in=weekly_scripts.values_list('slug', flat=True)):
            self.elapseTime2(sp, 13*31*24*60*60)
#        reschedule_weekly_polls('gem')
#        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675339', script__slug='edtrac_gem_weekly').time.date(), next_thursday.date())
        reschedule_weekly_polls()
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675349', script__slug='edtrac_teachers_weekly').time.date(), next_thursday.date())
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675319', script__slug='edtrac_head_teachers_weekly').time.date(), next_thursday.date())
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675329', script__slug='edtrac_smc_weekly').time.date(), next_thursday.date())

    def testRescheduleMonthlyPolls(self):
        ScriptProgress.objects.all().delete()
        self.register_reporter('teacher', '8675349')
        self.register_reporter('head teacher', '8675319')
        self.register_reporter('smc', '8675329')
        self.register_reporter('gem', '8675339')
        monthly_scripts = Script.objects.filter(slug__endswith='_monthly')
        Script.objects.filter(slug__in=monthly_scripts.values_list('slug', flat=True)).update(enabled=True)
        for sp in ScriptProgress.objects.filter(script__slug__in=monthly_scripts.values_list('slug', flat=True)):
            self.elapseTime2(sp, 13*31*24*60*60)
        self.assertEquals(ScriptProgress.objects.filter(script__slug__in=monthly_scripts.values_list('slug', flat=True))[0].time.year, datetime.datetime.now().year - 1)
        reschedule_monthly_polls('head teachers')
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675319', script__slug='edtrac_head_teachers_monthly').time.date(), _date_of_monthday('last').date())
        reschedule_monthly_polls('smc')
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675329', script__slug='edtrac_smc_monthly').time.date(), _date_of_monthday(5).date())
        for sp in ScriptProgress.objects.filter(script__slug__in=monthly_scripts.values_list('slug', flat=True)):
            self.elapseTime2(sp, 13*31*24*60*60)
        reschedule_monthly_polls()
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675319', script__slug='edtrac_head_teachers_monthly').time.date(), _date_of_monthday('last').date())
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675329', script__slug='edtrac_smc_monthly').time.date(), _date_of_monthday(5).date())

    def testRescheduleTermlyPolls(self):
        ScriptProgress.objects.all().delete()
        self.register_reporter('teacher', '8675349')
        self.register_reporter('head teacher', '8675319')
        self.register_reporter('smc', '8675329')
        self.register_reporter('gem', '8675339')
        termly_scripts = Script.objects.filter(slug__endswith='_termly')
        Script.objects.filter(slug__in=termly_scripts.values_list('slug', flat=True)).update(enabled=True)
        for sp in ScriptProgress.objects.filter(script__slug__in=termly_scripts.values_list('slug', flat=True)):
            self.elapseTime2(sp, 13*31*24*60*60)
        reschedule_termly_polls('head teachers')
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675319', script__slug='edtrac_head_teachers_termly').time.date(), _next_term_question_date().date())
        reschedule_termly_polls('smc')
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675329', script__slug='edtrac_smc_termly').time.date(), _next_term_question_date(rght=True).date())
        for sp in ScriptProgress.objects.filter(script__slug__in=termly_scripts.values_list('slug', flat=True)):
            self.elapseTime2(sp, 13*31*24*60*60)
        reschedule_termly_polls()
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675319', script__slug='edtrac_head_teachers_termly').time.date(), _next_term_question_date().date())
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675329', script__slug='edtrac_smc_termly').time.date(), _next_term_question_date(rght=True).date())
        for sp in ScriptProgress.objects.filter(script__slug__in=termly_scripts.values_list('slug', flat=True)):
            self.elapseTime2(sp, 13*31*24*60*60)
        reschedule_termly_polls('smc', date='2012-4-16')
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675329', script__slug='edtrac_smc_termly').time.date(), datetime.datetime(2012, 4, 16).date())
        for sp in ScriptProgress.objects.filter(script__slug__in=termly_scripts.values_list('slug', flat=True)):
            self.elapseTime2(sp, 13*31*24*60*60)
        reschedule_termly_polls('all', '2012-4-17')
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675319', script__slug='edtrac_head_teachers_termly').time.date(), datetime.datetime(2012, 4, 17).date())
        self.assertEquals(ScriptProgress.objects.get(connection__identity='8675329', script__slug='edtrac_smc_termly').time.date(), datetime.datetime(2012, 4, 17).date())