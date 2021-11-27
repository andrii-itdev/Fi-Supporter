
from __future__ import annotations
import pprint
from typing import Iterator, Type

""" Registry Manipulations"""

from io import TextIOWrapper
import winreg as reg
import os

APPLICATION_NAME = "fi-supporter"

currentUserKey = reg.HKEY_CURRENT_USER
allUsersKey = reg.HKEY_LOCAL_MACHINE
keyValue = "Software\Microsoft\Windows\CurrentVersion\Run"


def setRegistryKey(path, regKeyName, open):
    reg.SetValueEx(open, regKeyName, 0, reg.REG_SZ, path)

def tryAddToRegistry(path : str, regKeyName : str, all_users : bool = False):
    
    keyCategory = (allUsersKey if all_users else currentUserKey)
    keyType = reg.ConnectRegistry(None, keyCategory)
    open = reg.OpenKey(keyType, keyValue, 0, reg.KEY_ALL_ACCESS)
    try:
        #open = reg.OpenKey(keyType, regKeyName)
        value, type = reg.QueryValueEx(open, regKeyName)
        if not (type == reg.REG_SZ and value == path):
            setRegistryKey(path, regKeyName, open)
    except FileNotFoundError:
        setRegistryKey(path, regKeyName, open)
    finally:
        reg.CloseKey(open)

""" Helpers """

import json

ERROR = "Error: "
WARNING = "Wraning: "

def raiseError(message : str):
    print(ERROR + message)
    raise Exception(message)

def raiseWarning(message : str):
    print(WARNING + message)

def pathIfExists(filePath : str) -> str | None:
    if filePath and path.exists(filePath):
        return filePath
    else:
        raiseWarning(f"Can't find the path '{filePath}'")
        return None

def existentPaths(paths : Iterator[str]) -> Iterator[str]:
    for p in paths:
        existentPath = pathIfExists(p)
        if existentPath:
            yield existentPath


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, o: any) -> any:
        if type(o).__name__ == 'Configuration' or type(o).__name__ == 'Include' or type(o).__name__ == 'Exclude':
            return o.__dict__
        else:
            return json.JSONEncoder.default(self, o)

def printConfiguration(config):
    s = json.dumps(config, cls=CustomJsonEncoder, indent=4)
    print("\nConfiguration: \n" + s)

""" Configuration Part """

import os.path as path

INCLUDES = 'includes'
EXCLUDES = 'excludes'
PATHS = 'paths'
TARGET_PATH = 'targetPath'


class Exclude:
    paths : list[str]
    includes : list[Include]

    def __init__(self, paths : list[str], includes : list[Include]) -> None:
        self.paths = paths
        self.includes = includes

    @staticmethod
    def parseIncludes(obj : dict, defaultTargetPath = None) -> list[Include] | None:
        includesObj = obj.get(INCLUDES)
        if includesObj and len(includesObj) > 0:  
            includes = [Include.fromObject(obj, defaultTargetPath) for obj in includesObj if obj]
            includes = list(filter(None, includes))
            if len(includes) > 0:
                return includes
        return None
        
    @staticmethod
    def fromObject(obj : dict, defaultTargetPath = None) -> Exclude:
        paths = list(obj.get(PATHS))
        if paths:
            paths = list(existentPaths(paths))
        else:
            return None

        includes = Exclude.parseIncludes(obj, defaultTargetPath)

        return Exclude(paths, includes)
    
    def __repr__(self) -> str:
        return str(self.__dict__)

class Include:
    includesPaths : list[str]
    targetPath : str
    excludes : list[Exclude]

    def __init__(self, includes : list[str], targetPath : str, excludes : list[Exclude]) -> None:
        self.includesPaths = includes
        self.targetPath = targetPath
        self.excludes = excludes

    @staticmethod
    def fromObject(obj : dict, defaultTargetPath = None) -> Include:
        paths = list(obj.get(PATHS))
        if paths:
            #paths = list(filter(None, paths))
            paths = list(existentPaths(paths)) #[realPath for realPath in paths if realPath and path.exists(realPath)]
        else:
            return None
        
        targetPath = obj.get(TARGET_PATH)
        if not targetPath or not path.exists(targetPath):
            if defaultTargetPath:
                targetPath = defaultTargetPath
            else:
                raiseError(f"Incorrect configuration. '{TARGET_PATH}' is {'incorrect' if targetPath else 'unspecified'} at the root level")
        
        excludesList = obj.get(EXCLUDES)
        if excludesList and len(excludesList):
            excludes = [Exclude.fromObject(excludeObj, targetPath) for excludeObj in excludesList]
            excludes = list(filter(None, excludes))
        else:
            excludes = None

        return Include(paths, targetPath, excludes)
    
    def __repr__(self) -> str:
        return str(self.__dict__)

class Configuration:

    includes : list[Include]
    
    def __init__(self, includes : list[Include]):
        self.includes = includes

    @staticmethod
    def fromObj(obj : dict) -> Configuration:
        includes = Exclude.parseIncludes(obj)
        if includes:
            return Configuration(includes)
        raiseError("Incorrect configuration. No includes specified")

    @staticmethod
    def fromString(contents : str) -> Configuration:
        return Configuration.fromObj(json.loads(contents))

    @staticmethod
    def fromFile(fi : TextIOWrapper) -> Configuration:
        return Configuration.fromString(fi.read())

    def __repr__(self) -> str:
        #return f"Configuration:\n{self.includes}"
        return str(self.__dict__)
        

configFileName = "config.json"
configTemplate = """{
    "includes" : [
        {
            "paths" : [""],
            "targetPath" : "",
            "excludes" : [
                {
                    "paths" : [""],
                    "includes" : {
                    }
                }
            ]
        }
    ]
}"""


""" Ensure Backuped   """

def ensureDataIsBackuped(config : Configuration):
    pass


""" 
        Main 
"""

#import pprint

TITLE = "FI-SUPPORTER version 0.1\n"


def readConfig() -> Configuration :
    if path.exists(configFileName):
        with open(configFileName, 'r') as configFile:
            return Configuration.fromFile(configFile)
    else:
        with open(configFileName, 'w') as configFile:
            configFile.write(configTemplate)
            raiseError("Created config. Modify the configuration file and restart the application after that")

def run():
    input()
    input()

def main():
    
    print(TITLE)
    # currentPath = os.path.dirname()
    # address = os.join(currentPath, fileName)
    path = os.path.realpath(__file__)
    command = "python " + path
    #_, tail = os.path.split(path)
    #registryKeyName = tail.split(".")[0]
    #print(f"Trying to add to registry key '{registryKeyName}' for '{path}'")
    tryAddToRegistry(path, APPLICATION_NAME)
    config = readConfig()
    printConfiguration(config)
    ensureDataIsBackuped(config)
    run()

if __name__ == "__main__":
    main()

