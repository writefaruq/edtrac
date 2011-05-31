import datetime

from django.core.management.base import BaseCommand
import traceback
from rapidsms.models import Contact, Connection, Backend

from rapidsms_httprouter.models import Message
from rapidsms_httprouter.router import get_router

from django.db import transaction

from rapidsms.messages.outgoing import OutgoingMessage

from script.utils.outgoing import check_progress
from script.models import ScriptProgress
from optparse import OptionParser, make_option
import datetime

class Command(BaseCommand):

    option_list = BaseCommand.option_list + (
        make_option("-e", "--early", dest="e"),
        make_option("-l", "--late", dest="l")
    )

    @transaction.commit_manually
    def handle(self, **options):
        current = datetime.datetime.now()
        if current.hour in range(int(options['e']),int(options['l'])):
            try:
                router = get_router()
                for connection in ScriptProgress.objects.values_list('connection', flat=True).distinct():
                    connection=Connection.objects.get(pk=connection)
                    response = check_progress(connection)
                    if response:
                        if type(response) == Email and connection.contact and connection.contact.user:
                            response.recipients.clear()
                            response.recipients.add(connection.contact.user)
                            response.send()
                        else:
                            router.add_outgoing(connection, response)
                    transaction.commit()
                    if datetime.datetime.now() - current > datetime.timedelta(seconds=35):
                        return
            except Exception, exc:
                transaction.rollback()
                print traceback.format_exc(exc)
