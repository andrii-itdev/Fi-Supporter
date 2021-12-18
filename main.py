
from __future__ import annotations
from abc import abstractmethod
from typing import Generic, Iterator, List, Type, TypeVar

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

ERROR = "Error"
WARNING = "Warning"

INCORRECT_CONFIG_CAT = "Incorrect configuration"
COPY_FILES = "Unable to copy"
FS_ERROR = "File system access error"

log = open("events.log", "w")

def raiseError(message : str, category : str):
    msg = f"{ERROR}: {category}. {message}{os.linesep}"
    print(msg, end='')
    log.writelines(msg + '\n')
    raise Exception(message)

def raiseWarning(message : str, category : str):
    msg = f"{WARNING}: {category}. {message}{os.linesep}"
    print(msg, end='')
    log.writelines(msg)

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
            yield path.abspath(str(existentPath))


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


class ConfigurationRule:
    @abstractmethod
    def accept(self, visitor : ConfigurationVisitor):
        pass

# class Exclude(ConfigurationRule):
#     paths : list[str]
#     includes : list[Include]

#     def __init__(self, paths : list[str], includes : list[Include]) -> None:
#         self.paths = paths
#         self.includes = includes
        
#     @staticmethod
#     def fromObject(obj : dict, defaultTargetPath = None) -> Exclude:
#         paths = list(obj.get(PATHS))
#         if paths:
#             paths = list(existentPaths(paths))
#         else:
#             return None

#         includes = Exclude.parseIncludes(obj, defaultTargetPath)

#         return Exclude(paths, includes)
    
#     def accept(self, visitor : ConfigurationVisitor):
#         visitor.visitExclude(self)
    
#     def __repr__(self) -> str:
#         return str(self.__dict__)

class Include(ConfigurationRule):
    includePaths : list[str]
    targetPath : str
    excludes : list[str]

    def __init__(self, includes : list[str], targetPath : str, excludes : list[str]) -> None:
        self.includePaths = includes
        self.targetPath = targetPath
        self.excludes = excludes

    @staticmethod
    def fromObject(obj : dict) -> Include:
        paths = list(obj.get(PATHS))
        if not paths or not len(paths):
            raiseError("You have not specified any include paths")
        
        paths = list(existentPaths(paths))

        if not len(paths):
            raiseError("You have not specified any existent include paths", INCORRECT_CONFIG_CAT)
        
        targetPath = path.abspath(str(obj.get(TARGET_PATH)))

        if not targetPath or not path.exists(targetPath):
            raiseError(f"'{TARGET_PATH}' is {'incorrect' if targetPath else 'unspecified'}", INCORRECT_CONFIG_CAT)
        
        excludes = obj.get(EXCLUDES)
        if excludes and len(excludes):
            excludes = list(existentPaths(excludes))
        else:
            excludes = []

        return Include(paths, targetPath, excludes)
    
    def accept(self, visitor : ConfigurationVisitor):
        visitor.visitInclude(self)
        if self.excludes:
            for exclude in list(self.excludes):
                visitor.visitExclude(exclude)
    
    def __repr__(self) -> str:
        return str(self.__dict__)

class Configuration(ConfigurationRule):

    includes : list[Include]
    
    def __init__(self, includes : list[Include]):
        self.includes = includes
    
    @staticmethod
    def parseIncludes(obj : dict) -> list[Include] | None:
        includesObj = obj.get(INCLUDES)
        if includesObj and len(includesObj) > 0:
            includes : list[Include] = list();
            for includeObj in includesObj:
                if includeObj:
                    include = Include.fromObject(includeObj)
                    if include:
                        includes.append(include)
            if (len(includes)):
                return includes
        return None

    @staticmethod
    def fromObj(obj : dict) -> Configuration:
        includes = Configuration.parseIncludes(obj)
        if includes or len(includes):
            return Configuration(includes)
        raiseError("No includes specified", INCORRECT_CONFIG_CAT)

    @staticmethod
    def fromString(contents : str) -> Configuration:
        return Configuration.fromObj(json.loads(contents))

    @staticmethod
    def fromFile(fi : TextIOWrapper) -> Configuration:
        return Configuration.fromString(fi.read())

    def accept(self, visitor : ConfigurationVisitor):
        visitor.visitConfiguration(self)
        for include in self.includes:
            include.accept(visitor)

    def __repr__(self) -> str:
        return str(self.__dict__)
    

configFileName = "config.json"
configTemplate = """{
    "includes" : [
        {
            "paths" : [""], 
            "targetPath" : "",
            "excludes" : [""]
        },
        {
            "paths" : [""],
            "targetPath" : ""
        }
    ]
}"""

""" Configuration Manipulations """

class ConfigurationVisitor:
    @abstractmethod
    def visitConfiguration(self, config : Configuration) -> None:
        pass
    
    @abstractmethod
    def visitInclude(self, include : Include) -> None:
        pass

    @abstractmethod
    def visitExclude(self, exclude : str) -> None:
        pass

class ConfigurationValidationVisitor(ConfigurationVisitor):
    parentInclude : Include

    def __init__(self) -> None:
        super().__init__()

    def visitConfiguration(self, config : Configuration) -> None:
        super().visitConfiguration(config)
    
    def visitInclude(self, include : Include) -> None:
        self.parentInclude = include
        super().visitInclude(include)
    
    def visitExclude(self, exclude : str) -> None:
        isSub = False
        for includePath in self.parentInclude.includePaths:
            if exclude.startswith(includePath):
                isSub = True
        if not isSub:
            raiseWarning(f'Exclude path "{exclude}" is not under any folder "{self.parentInclude.includePaths}"', INCORRECT_CONFIG_CAT)
            self.parentInclude.excludes.remove(exclude)
        super().visitExclude(exclude)


""" Ensure Backuped """

import shutil

def tryCopy2(src, dst, excludes : list[str], follow_symlinks=True):
    try:
        # dontCopy = False
        # for exclude in excludes:
        #     if src.startswith(exclude):
        #         dontCopy = True
        #         break
        # if not dontCopy:
            shutil.copy2(src, dst)
    except OSError as e:
        raiseWarning(e, COPY_FILES)

def ensureDataIsBackuped(config : Configuration):
    for include in config.includes:
        for sourcePath in include.includePaths:
            try:
                ignorePatterns = [
                        exclude.removeprefix(includeSrc + os.sep)
                        for exclude in include.excludes 
                        for includeSrc in include.includePaths 
                        if exclude.startswith(includeSrc)
                    ]
                shutil.copytree(
                    sourcePath, include.targetPath, 
                    dirs_exist_ok=True, 
                    ignore=shutil.ignore_patterns(*ignorePatterns),
                    copy_function=lambda src, dst: tryCopy2(src, dst, include.excludes)
                    )
            except OSError as osErr:
                raiseError(str(osErr), FS_ERROR)

""" 
        Main 
"""

TITLE = "FI-SUPPORTER version 0.1\n"

def tryReadConfig() -> Configuration :
    try:
        if path.exists(configFileName):
            with open(configFileName, 'r') as configFile:
                return Configuration.fromFile(configFile)
        else:
            with open(configFileName, 'w') as configFile:
                configFile.write(configTemplate)
                raiseError("Created config. Modify the configuration file and restart the application after that")
    except OSError as osErr:
        raiseError(str(osErr), FS_ERROR)

def runMonitor():
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
    config = tryReadConfig()
    config.accept(ConfigurationValidationVisitor())
    printConfiguration(config)
    ensureDataIsBackuped(config)
    runMonitor()

if __name__ == "__main__":
    main()

