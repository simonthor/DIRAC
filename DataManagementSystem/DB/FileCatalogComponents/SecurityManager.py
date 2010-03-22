########################################################################
# $HeadURL:  $
########################################################################
""" DIRAC FileCatalog Security Manager mix-in class
"""

__RCSID__ = "$Id:  $"

import time,os
from DIRAC import S_OK, S_ERROR, gConfig

class SecurityManagerBase:
  
  def __init__(self,database=False):
    self.db = database
    
  def setDatabase(self,database):
    self.db = database
    
  def hasAccess(self,opType,paths,credDict):
    successful = {}
    if not opType.lower() in ['read','write']:
      return S_ERROR("Operation type not known")
    for path in paths:
      successful[path] = False
    resDict = {'Successful':successful,'Failed':{}}
    return S_OK(resDict)

  def hasAdminAccess(self,credDict):
    if credDict.get('group','') == 'diracAdmin':
      return S_OK(True)
    return S_OK(False)

class NoSecurityManager(SecurityManagerBase):

  def hasAccess(self,opType,paths,credDict):
    successful = {}
    for path in paths:
      successful[path] = True
    resDict = {'Successful':successful,'Failed':{}}
    return S_OK(resDict)

  def hasAdminAccess(self,credDict):
    return S_OK(True)

class DirectorySecurityManager(SecurityManagerBase):
  
  def hasAccess(self,opType,paths,credDict):
    successful = {}
    if not opType in ['Read','Write']:
      return S_ERROR("Operation type not known")
    if self.db.globalReadAccess and (opType.lower() == 'read'):
      for path in paths:
        successful[path] = True
      resDict = {'Successful':successful,'Failed':{}}
      return S_OK(resDict)
    toGet = dict(zip(paths,[ [path] for path in paths ]))
    permissions = {}
    failed = {}
    while toGet:
      paths = toGet.keys()
      res = self.db.dtree.getPathPermissions(paths,credDict)
      if not res['OK']:
        return res
      for path,mode in res['Value']['Successful'].items():
        for resolvedPath in toGet[path]:
          permissions[resolvedPath] = mode
        toGet.pop(path)  
      for path,error in res['Value']['Failed'].items():
        if error != 'No such file or directory':
          for resolvedPath in toGet[path]:
            failed[resolvedPath] = error
          toGet.pop(path)
      for path,resolvedPaths in toGet.items():
        if path == '/':
          for resolvedPath in resolvedPaths:
            permissions[path] = {'Read':True,'Write':True,'Execute':True}
        if not toGet.has_key(os.path.dirname(path)):
          toGet[os.path.dirname(path)] = []
        toGet[os.path.dirname(path)] += resolvedPaths
        toGet.pop(path)
    for path,permDict in permissions.items():
      if permDict[opType]:
        successful[path] = True
      else:
        successful[path] = False
    resDict = {'Successful':successful,'Failed':failed}
    return S_OK(resDict)

class FullSecurityManager(SecurityManagerBase):
  pass
