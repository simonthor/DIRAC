""" Module collecting functions dealing with the GLUE2 information schema

:author: A.Sailer

"""

from pprint import pformat

from DIRAC import gLogger
from DIRAC.Core.Utilities.ReturnValues import S_OK, S_ERROR


def __ldapsearchBDII(*args, **kwargs):
  """ wrap `DIRAC.Core.Utilities.Grid.ldapsearchBDII` to avoid circular import """
  from DIRAC.Core.Utilities.Grid import ldapsearchBDII
  return ldapsearchBDII(*args, **kwargs)


def getGlue2CEInfo(vo, host):
  """ call ldap for GLUE2 and get information

  :param str vo: Virtual Organisation
  :param str host: host to query for information
  :returns: result structure with result['Value'][siteID]['CEs'][ceID]['Queues'][queueName]. For
               each siteID, ceID, queueName all the GLUE2 parameters are retrieved
  """

  # get all Policies allowing given VO
  filt = "(&(objectClass=GLUE2Policy)(GLUE2PolicyRule=VO:%s))" % vo
  polResVO = __ldapsearchBDII(filt=filt, attr=None, host=host, base="o=glue", selectionString="GLUE2")
  if not polResVO['OK']:
    return polResVO

  # get all Policies allowing given vo, yes, lowercase is a Thing...
  filt = "(&(objectClass=GLUE2Policy)(GLUE2PolicyRule=vo:%s))" % vo
  polResvo = __ldapsearchBDII(filt=filt, attr=None, host=host, base="o=glue", selectionString="GLUE2")

  if not polResvo['OK']:
    return polResvo
  polRes = list(polResVO['Value'] + polResvo['Value'])

  gLogger.notice("Found %s policies for this VO %s" % (len(polRes), vo))
  siteDict = {}
  # get all shares for this policy
  for policyValues in polRes:
    shareID = policyValues['attr'].get('GLUE2MappingPolicyShareForeignKey', None)
    policyID = policyValues['attr']['GLUE2PolicyID']
    siteName = policyValues['attr']['dn'].split('GLUE2DomainID=')[1].split(',', 1)[0]
    if shareID is None:  # policy not pointing to ComputingInformation
      gLogger.debug("Policy %s does not point to computing information" % (policyID,))
      continue
    gLogger.notice("%s policy %s pointing to %s " % (siteName, policyID, shareID))
    gLogger.debug("Policy values:\n%s" % pformat(policyValues))
    filt = "(&(objectClass=GLUE2ComputingShare)(GLUE2ShareID=%s))" % shareID
    shareRes = __ldapsearchBDII(filt=filt, attr=None, host=host, base="o=glue", selectionString="GLUE2")
    if not shareRes['OK']:
      gLogger.error("Could not get computing share information for %s: %s" % (shareID, shareRes['Message']))
      continue
    if not shareRes['Value']:
      gLogger.warn("Did not not find any computing share information for %s" % (shareID, ))
      continue
    siteDict.setdefault(siteName, {'CEs': {}})
    for shareInfo in shareRes['Value']:
      gLogger.debug("Found computing share:\n%s" % pformat(shareInfo))
      shareEndpoints = shareInfo['attr'].get('GLUE2ShareEndpointForeignKey', [])
      ceInfo = __getGlue2ShareInfo(host, shareEndpoints, shareInfo['attr'], siteDict[siteName]['CEs'])
      if not ceInfo['OK']:
        gLogger.error("Could not get CE info", ceInfo['Message'])
        continue
      gLogger.debug("Found ceInfo:\n%s" % pformat(siteDict[siteName]['CEs']))

  gLogger.debug("Found Sites:\n%s" % pformat(siteDict))

  return S_OK(siteDict)


def __getGlue2ShareInfo(host, shareEndpoints, shareInfoDict, cesDict):
  """ get information from endpoints, which are the CE at a Site

  :param str host: BDII host to query
  :param list shareEndpoints: list of endpoint names
  :param dict shareInfoDict: dictionary of GLUE2 parameters belonging to the ComputingShare
  :param dict cesDict: dictionary with the CE information, will be modified in this function to add the information of the share
  :returns: result structure S_OK/S_ERROR
  """

  ceInfo = {}
  ceInfo['MaxWaitingJobs'] = shareInfoDict.get('GLUE2ComputingShareMaxWaitingJobs', '-1')  # This is not used
  ceInfo['Queues'] = {}
  queueInfo = {}
  queueInfo['GlueCEStateStatus'] = shareInfoDict['GLUE2ComputingShareServingState']
  queueInfo['GlueCEPolicyMaxCPUTime'] = str(int(shareInfoDict.get('GLUE2ComputingShareMaxCPUTime', 86400)) / 60)
  queueInfo['GlueCEPolicyMaxWallClockTime'] = str(int(shareInfoDict.get('GLUE2ComputingShareMaxWallTime', 86400)) / 60)
  queueInfo['GlueCEInfoTotalCPUs'] = shareInfoDict.get('GLUE2ComputingShareMaxRunningJobs', '10000')
  queueInfo['GlueCECapability'] = []
  executionEnvironment = shareInfoDict['GLUE2ComputingShareExecutionEnvironmentForeignKey']
  resExeInfo = __getGlue2ExecutionEnvironmentInfo(host, executionEnvironment)
  if not resExeInfo['OK']:
    return S_ERROR("Cannot get execution environment info", resExeInfo['Message'])
  ceInfo.update(resExeInfo['Value'])
  if isinstance(shareEndpoints, basestring):
    shareEndpoints = [shareEndpoints]
  for endpoint in shareEndpoints:
    ceType = endpoint.rsplit('.', 1)[1]
    # get queue Name, in CREAM this is behind GLUE2entityOtherInfo...
    if ceType == 'CREAM':
      for otherInfo in shareInfoDict['GLUE2EntityOtherInfo']:
        if otherInfo.startswith('CREAMCEId'):
          queueName = otherInfo.split('/', 1)[1]
      # cream time still in minutes
      queueInfo['GlueCEPolicyMaxCPUTime'] = str(int(queueInfo['GlueCEPolicyMaxCPUTime']) * 60)
      queueInfo['GlueCEPolicyMaxWallClockTime'] = str(int(queueInfo['GlueCEPolicyMaxWallClockTime']) * 60)

    elif ceType.endswith('HTCondorCE'):
      ceType = 'HTCondorCE'
      queueName = 'condor'

    queueInfo['GlueCEImplementationName'] = ceType

    ceName = endpoint.split('_', 1)[0]
    cesDict.setdefault(ceName, {})
    existingQueues = dict(cesDict[ceName].get('Queues', {}))
    existingQueues[queueName] = queueInfo
    ceInfo['Queues'] = existingQueues
    cesDict[ceName].update(ceInfo)

  # ARC CEs do not have endpoints, we have to try something else to get the information about the queue etc.
  if not shareEndpoints and shareInfoDict['GLUE2ShareID'].startswith('urn:ogf'):
    exeInfo = dict(resExeInfo['Value'])  # silence pylint about tuples
    ceType = 'ARC'
    managerName = exeInfo.pop('MANAGER', '').split(' ', 1)[0].rsplit(':', 1)[1]
    managerName = managerName.capitalize() if managerName == 'condor' else managerName
    queueName = 'nordugrid-%s-%s' % (managerName, shareInfoDict['GLUE2ComputingShareMappingQueue'])
    ceName = shareInfoDict['GLUE2ShareID'].split('ComputingShare:')[1].split(':')[0]
    cesDict.setdefault(ceName, {})
    existingQueues = dict(cesDict[ceName].get('Queues', {}))
    existingQueues[queueName] = queueInfo
    ceInfo['Queues'] = existingQueues
    cesDict[ceName].update(ceInfo)

  return S_OK()


def __getGlue2ExecutionEnvironmentInfo(host, executionEnvironment):
  """ get the information about OS version, architecture, memory from GLUE2 ExecutionEnvironment

  :param str host: BDII host to query
  :param str exeInfo: name of the execution environment to get some information from
  :returns: result structure with information in Glue1 schema to be consumed later elsewhere
  """
  filt = "(&(objectClass=GLUE2ExecutionEnvironment)(GLUE2ResourceID=%s))" % executionEnvironment
  response = __ldapsearchBDII(filt=filt, attr=None, host=host, base="o=glue", selectionString="GLUE2")
  if not response['OK']:
    return response
  if len(response['Value']) != 1:
    return S_ERROR("Unexpected response for ExecutionEnvironment")
  gLogger.debug("Found ExecutionEnvironment %s:\n%s" % (executionEnvironment, pformat(response)))
  exeInfo = response['Value'][0]['attr']  # pylint: disable=unsubscriptable-object
  maxRam = exeInfo.get('GLUE2ExecutionEnvironmentMainMemorySize', '')
  architecture = exeInfo.get('GLUE2ExecutionEnvironmentPlatform', '')
  architecture = 'x86_64' if architecture == 'amd64' else architecture
  architecture = 'x86_64' if architecture == 'UNDEFINEDVALUE' else architecture
  osFamily = exeInfo.get('GLUE2ExecutionEnvironmentOSFamily', '')  # e.g. linux
  osName = exeInfo.get('GLUE2ExecutionEnvironmentOSName', '')
  osVersion = exeInfo.get('GLUE2ExecutionEnvironmentOSVersion', '')
  manager = exeInfo.get('GLUE2ExecutionEnvironmentComputingManagerForeignKey', '')
  # translate to Glue1 like keys, because that is used later on
  infoDict = {'GlueHostMainMemoryRAMSize': maxRam,
              'GlueHostOperatingSystemVersion': osName,
              'GlueHostOperatingSystemName': osFamily,
              'GlueHostOperatingSystemRelease': osVersion,
              'GlueHostArchitecturePlatformType': architecture,
              'MANAGER': manager,  # to create the ARC QueueName mostly
             }

  return S_OK(infoDict)
