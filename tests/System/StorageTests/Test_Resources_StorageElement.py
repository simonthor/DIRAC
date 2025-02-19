"""
This integration tests will perform basic operations on a storage element, depending on which protocols are available.
It creates a local hierarchy, and then tries to upload, download, remove, get metadata etc

Examples:
<python Test_Resources_StorageElement.py CERN-GFAL2>: will test all the gfal2 plugins defined for CERN-GFAL2
<python Test_Resources_StorageElement.py CERN-GFAL2 GFAL2_XROOT>: will test the GFAL2_XROOT plugins defined for CERN-GFAL2


"""
from asyncio import protocols
import os
import sys
import tempfile
import shutil

import pytest


from DIRAC.Core.Base.Script import parseCommandLine


argv, sys.argv = sys.argv, ["Dummy"]

parseCommandLine()
from DIRAC.Resources.Storage.StorageElement import StorageElement
from DIRAC.Core.Security.ProxyInfo import getProxyInfo
from DIRAC.Core.Utilities.Adler import fileAdler
from DIRAC.Core.Utilities.File import getSize
from DIRAC.ConfigurationSystem.Client.Helpers.Registry import getVOForGroup
from DIRAC.Core.Utilities.ReturnValues import S_OK, S_ERROR, convertToReturnValue, returnValueOrRaise


# pylint: disable=unspecified-encoding

# Size in bytes of the file we want to produce
FILE_SIZE = 5 * 1024  # 5kB


@pytest.fixture(scope="module")
def prepare_local_testDir():
    """Create the following structure in a local directory
    FolderA
    -- FolderAA
    -- -- FileAA
    -- FileA
    FolderB
    -- FileB
    File1
    File2
    File3

    """

    proxyInfo = returnValueOrRaise(getProxyInfo())

    username = proxyInfo["username"]
    vo = ""
    if "group" in proxyInfo:
        vo = getVOForGroup(proxyInfo["group"])

    destinationPath = f"/{vo}/user/{username[0]}/{username}/gfaltests"
    # local path containing test files. There should be a folder called Workflow containing (the files can be simple textfiles)

    def _mul(txt):
        """Multiply the input text enough time so that we
        reach the expected file size
        """
        return txt * (max(1, int(FILE_SIZE / len(txt))))

    # create the local structure
    localWorkDir = tempfile.mkdtemp()
    try:
        workPath = os.path.join(localWorkDir, "Workflow")
        os.mkdir(workPath)

        os.mkdir(os.path.join(workPath, "FolderA"))
        with open(os.path.join(workPath, "FolderA", "FileA"), "wt") as f:
            f.write(_mul("FileA"))

        os.mkdir(os.path.join(workPath, "FolderA", "FolderAA"))
        with open(os.path.join(workPath, "FolderA", "FolderAA", "FileAA"), "w") as f:
            f.write(_mul("FileAA"))

        os.mkdir(os.path.join(workPath, "FolderB"))
        with open(os.path.join(workPath, "FolderB", "FileB"), "w") as f:
            f.write(_mul("FileB"))

        for fn in ["File1", "File2", "File3"]:
            with open(os.path.join(workPath, fn), "w") as f:
                f.write(_mul(fn))

    except FileExistsError:
        pass

    yield localWorkDir, destinationPath
    shutil.rmtree(localWorkDir)


@pytest.fixture
def prepare_seObj_fixture(seName, protocolSection, prepare_local_testDir):

    localWorkDir, destinationPath = prepare_local_testDir

    # When testing for a given plugin, this plugin might not be able to
    # write or read. In this case, we use this specific plugins
    # ONLY for the operations it is allowed to
    specSE = StorageElement(seName, protocolSections=protocolSection)
    genericSE = StorageElement(seName)

    pluginProtocol = specSE.protocolOptions[0]["Protocol"]
    if pluginProtocol in specSE.localAccessProtocolList:
        print("Using specific SE with %s only for reading" % protocolSection)
        readSE = specSE
    else:
        print("Plugin %s is not available for read. Use a generic SE" % protocolSection)
        readSE = genericSE

    if pluginProtocol in specSE.localWriteProtocolList:
        print("Using specific SE with %s only for writing" % protocolSection)
        writeSE = specSE
    else:
        print("Plugin %s is not available for write. Use a generic SE" % protocolSection)
        writeSE = genericSE

    # Make sure we are testing the specific plugin at least for one
    assert readSE == specSE or writeSE == specSE, "Using only generic SE does not make sense!!"

    yield seName, protocolSection, readSE, writeSE, localWorkDir, destinationPath

    print("==================================================")
    print("==== Removing the older Directory ================")
    workflow_folder = destinationPath + "/Workflow"
    res = writeSE.removeDirectory(workflow_folder)
    if not res["OK"]:
        print("basicTest.clearDirectory: Workflow folder maybe not empty")
    print("==================================================")


@pytest.fixture
def fixture_using_other(seName, protocolSection):
    print("I am first preparing")

    return seName + "after", protocolSection + "after"


def test_storage_element(prepare_seObj_fixture):
    """Perform basic operations on a given storage Elements"""

    seName, protocolSection, readSE, writeSE, localWorkDir, destinationPath = prepare_seObj_fixture
    print(f"{seName}: {protocolSection}")
    assert not seName.isalpha()

    putDir = {
        os.path.join(destinationPath, "Workflow/FolderA"): os.path.join(localWorkDir, "Workflow/FolderA"),
        os.path.join(destinationPath, "Workflow/FolderB"): os.path.join(localWorkDir, "Workflow/FolderB"),
    }

    createDir = [
        os.path.join(destinationPath, "Workflow/FolderA/FolderAA"),
        os.path.join(destinationPath, "Workflow/FolderA/FolderABA"),
        os.path.join(destinationPath, "Workflow/FolderA/FolderAAB"),
    ]

    putFile = {
        os.path.join(destinationPath, "Workflow/FolderA/File1"): os.path.join(localWorkDir, "Workflow/File1"),
        os.path.join(destinationPath, "Workflow/FolderAA/File1"): os.path.join(localWorkDir, "Workflow/File1"),
        os.path.join(destinationPath, "Workflow/FolderBB/File2"): os.path.join(localWorkDir, "Workflow/File2"),
        os.path.join(destinationPath, "Workflow/FolderB/File2"): os.path.join(localWorkDir, "Workflow/File2"),
        os.path.join(destinationPath, "Workflow/File3"): os.path.join(localWorkDir, "Workflow/File3"),
    }

    isFile = {
        os.path.join(destinationPath, "Workflow/FolderA/File1"): os.path.join(localWorkDir, "Workflow/File1"),
        os.path.join(destinationPath, "Workflow/FolderB/FileB"): os.path.join(localWorkDir, "Workflow/FolderB/FileB"),
    }

    listDir = [
        os.path.join(destinationPath, "Workflow"),
        os.path.join(destinationPath, "Workflow/FolderA"),
        os.path.join(destinationPath, "Workflow/FolderB"),
    ]

    getDir = [
        os.path.join(destinationPath, "Workflow/FolderA"),
        os.path.join(destinationPath, "Workflow/FolderB"),
    ]

    removeFile = [os.path.join(destinationPath, "Workflow/FolderA/File1")]
    rmdir = [os.path.join(destinationPath, "Workflow")]

    ##### Computing local adler and size #####

    fileAdlers = {}
    fileSizes = {}

    for lfn, localFn in isFile.items():
        fileAdlers[lfn] = fileAdler(localFn)
        fileSizes[lfn] = getSize(localFn)

    ########## uploading directory #############
    res = writeSE.putDirectory(putDir)
    assert res["OK"], res
    # time.sleep(5)
    res = readSE.listDirectory(listDir)
    assert any(
        os.path.join(destinationPath, "Workflow/FolderA/FileA") in dictKey
        for dictKey in res["Value"]["Successful"][os.path.join(destinationPath, "Workflow/FolderA")]["Files"].keys()
    ), res
    assert any(
        os.path.join(destinationPath, "Workflow/FolderB/FileB") in dictKey
        for dictKey in res["Value"]["Successful"][os.path.join(destinationPath, "Workflow/FolderB")]["Files"].keys()
    ), res

    ########## createDir #############
    res = writeSE.createDirectory(createDir)
    assert res["OK"], res
    res = res["Value"]
    assert res["Successful"][createDir[0]], res
    assert res["Successful"][createDir[1]], res
    assert res["Successful"][createDir[2]], res

    ######## putFile ########
    res = writeSE.putFile(putFile)
    assert res["OK"], res
    # time.sleep(5)
    res = readSE.isFile(isFile)
    assert res["OK"], res
    assert all([x for x in res["Value"]["Successful"].values()])
    # self.assertEqual( res['Value']['Successful'][isFile[0]], True )
    # self.assertEqual( res['Value']['Successful'][isFile[1]], True )

    ######## getMetadata ###########
    res = readSE.getFileMetadata(isFile)
    assert res["OK"], res
    res = res["Value"]["Successful"]
    assert any(path in resKey for path in isFile for resKey in res.keys())

    # Checking that the checksums and sizes are correct
    for lfn in isFile:
        assert res[lfn]["Checksum"] == fileAdlers[lfn], f"{res[lfn]['Checksum']} != {fileAdlers[lfn]}"
        assert res[lfn]["Size"] == fileSizes[lfn], f"{res[lfn]['Size']} !=  {fileSizes[lfn]}"

    ####### getDirectory ######
    res = readSE.getDirectory(getDir, os.path.join(localWorkDir, "getDir"))
    assert res["OK"], res
    res = res["Value"]
    assert any(getDir[0] in dictKey for dictKey in res["Successful"]), res
    assert any(getDir[1] in dictKey for dictKey in res["Successful"]), res

    ###### removeFile ##########
    res = writeSE.removeFile(removeFile)
    assert res["OK"], res
    res = readSE.exists(removeFile)
    assert res["OK"], res
    assert not res["Value"]["Successful"][removeFile[0]], res

    ###### remove non existing file #####
    res = writeSE.removeFile(removeFile)
    assert res["OK"], res
    res = readSE.exists(removeFile)
    assert res["OK"], res
    assert not res["Value"]["Successful"][removeFile[0]], res

    ########### removing directory  ###########
    res = writeSE.removeDirectory(rmdir, True)

    res = readSE.exists(rmdir)
    assert res["OK"], res
    assert not res["Value"]["Successful"][rmdir[0]], res
