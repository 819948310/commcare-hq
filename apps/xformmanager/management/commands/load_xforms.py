""" This script deletes existing data and 
loads new data into the local CommCareHQ server """

from optparse import make_option
from django.core.management.base import LabelCommand, CommandError
from xformmanager.management.commands import util
from xformmanager.management.commands.reset_xforms import reset_xforms, reset_submits
import tarfile

class Command(LabelCommand):
    option_list = LabelCommand.option_list + (
        make_option('-p','--localport', action='store', dest='localport', \
                    default='8000', help='Port of local server'),
    )
    help = "Load data into CommCareHQ. Be sure to run './manage.py reset_xforms'" + \
           "if you want to start from a clean server."
    args = "<submissions_tar optional:schemata_tar>"
    label = 'tar file of exported schemata, tar file of exported submissions'
    
    def handle(self, *args, **options):
        if len(args) < 1:
            raise CommandError('Please specify %s.' % self.label)
        submissions = args[0]
        if len(args)>1: schemata = args[1]
        print "WARNING: Loading new data"
        util.are_you_sure()

        localport = options.get('localport', 8000)
        
        # make sure to load schemas before submissions
        if len(args)>1: load_schemata(localport, schemata)
        load_submissions(localport, submissions)
        
    def __del__(self):
        pass

def load_schemata(localport, schemata_file):
    """ This script loads new data into the local CommCareHQ server
    
    Arguments: 
    args[0] - tar file of exported schemata
    """
    if not tarfile.is_tarfile(schemata_file):
        fin = open(schemata_file)
        contents = fin.read(256)
        fin.close()
        if contents.find("No schemas") != -1:
            print "No new submissions"
        else:
            print "This is not a valid schemata file"
    else:
        localserver = "127.0.0.1:%s" % localport
        util.extract_and_process(schemata_file, util.submit_schema, localserver)
            
def load_submissions(localport, submissions_file):
    """ This script loads new data into the local CommCareHQ server
    
    Arguments: 
    args[0] - tar file of exported submissions
    """
    if not tarfile.is_tarfile(submissions_file):
        fin = open(submissions_file)
        contents = fin.read(256)
        fin.close()
        if contents.find("No submissions") != -1:
            print "No new schemas"
        else:
            print "This is not a valid submissions file"
    else:
        localserver = "127.0.0.1:%s" % localport
        util.extract_and_process(submissions_file, util.submit_form, localserver)
