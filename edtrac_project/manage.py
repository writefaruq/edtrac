#!/usr/bin/env python

import os
import sys





if __name__ == "__main__":
    sys.path.append("/home/fsarker/projects/rapidsms-sandbox/edtrac/edtrac_project")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings.local")
    #import pdb; pdb.set_trace()
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
