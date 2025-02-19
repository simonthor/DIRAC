#!/usr/bin/env python
""" Drop DBs from the MySQL server
"""
from DIRAC.Core.Base.Script import Script

Script.setUsageMessage(
    "\n".join(
        [
            __doc__.split("\n")[1],
            "Usage:",
            "  %s [options] ... DB ..." % Script.scriptName,
            "Arguments:",
            "  DB: Name of the Database (mandatory)",
        ]
    )
)
Script.parseCommandLine()
args = Script.getPositionalArgs()

if len(args) < 1:
    Script.showHelp(exitCode=1)

from DIRAC.FrameworkSystem.Client.ComponentInstaller import gComponentInstaller

gComponentInstaller.getMySQLPasswords()
for db in args:
    print(gComponentInstaller.execMySQL("DROP DATABASE IF EXISTS %s" % db))
