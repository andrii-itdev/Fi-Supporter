
from __future__ import annotations
from abc import abstractmethod
from typing import Generic, Iterator, List, Type, TypeVar

APPLICATION_NAME = "fi-supporter"
APP_VERSION = "0.1"
TITLE = APPLICATION_NAME.capitalize() + f" version {APP_VERSION}\n"

""" Registry Manipulations"""

from io import TextIOWrapper
import winreg as reg
import os

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

logFile : TextIOWrapper

def log(msg : str):
    if not msg.endswith(os.linesep):
        msg += os.linesep
    logFile.writelines(msg)

def notifyMessage(message : str, end=os.linesep):
    print(message, end=end)
    log(message)

def notify(message : str, category : str, type : str):
    msg = f"{type}: {category}. {message}{os.linesep}"
    notifyMessage(msg, end='')

def raiseError(message : str, category : str):
    notify(message, category, ERROR)
    raise Exception(message)

def raiseWarning(message : str, category : str):
    notify(message, category, WARNING)

def pathIfExists(filePath : str) -> str | None:
    if filePath and path.exists(filePath):
        return filePath
    else:
        raiseWarning(f"Can't find the path '{filePath}'", INCORRECT_CONFIG_CAT)
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

        if not targetPath:
            raiseError(f"'{TARGET_PATH}' is unspecified", INCORRECT_CONFIG_CAT)

        if not path.exists(targetPath):
            raiseWarning(f"'{TARGET_PATH}' does not exist, therefore this rule is ignored. Once this target path '{targetPath}' appears in file system the corresponding rule will be activated.", INCORRECT_CONFIG_CAT)
        
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
            raiseWarning(f'Exclude path "{exclude}" is not a subfolder of any "{self.parentInclude.includePaths}"', INCORRECT_CONFIG_CAT)
            self.parentInclude.excludes.remove(exclude)
        super().visitExclude(exclude)

""" Setup file system monitoring """

from watchdog.observers import Observer
from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent, PatternMatchingEventHandler
from watchdog.utils import patterns

class Watcher:
    sourcePath : str
    targetPath : str
    observer : Observer
    handler : FileSystemEventHandler

    def __init__(self, src : str, target : str) -> None:
        self.sourcePath = src
        self.targetPath = target
        self.observer = Observer()
    
    def configureObserver(self, ignorePatterns : any = []):
        self.ignorePaths = ignorePatterns
        self.handler = PatternMatchingEventHandler(
            "*", ignorePatterns, ignore_directories=False, case_sensitive=True)
        self.handler.on_created = self.on_created
        self.handler.on_deleted = self.on_deleted
        self.handler.on_modified = self.on_modified
        self.handler.on_moved = self.on_moved
    
    def run(self):
        if self.handler == None:
            self.configureObserver()
        self.observer.schedule(self.handler, self.sourcePath, recursive=True)
        self.observer.start()

    def stop(self):
        self.observer.stop()
        self.observer.join()

    def shouldIgnore(self, path : str) -> bool:
        for ignorePath in self.ignorePaths: 
            if path.startswith(os.path.join(self.sourcePath, ignorePath)):
                return True
        return False
    
    def on_created(self, event : FileSystemEvent):
        if self.shouldIgnore(event.src_path):
            return
        print(f"{event.src_path} has been created!")

    def on_deleted(self, event : FileSystemEvent):
        if self.shouldIgnore(event.src_path):
            return
        print(f"{event.src_path} has been deleted!")

    def on_modified(self, event : FileSystemEvent):
        if self.shouldIgnore(event.src_path):
            return
        print(f"{event.src_path} has been modified!")

    def on_moved(self, event : FileSystemMovedEvent):
        if self.shouldIgnore(event.src_path):
            return
        print(f"{event.src_path} has been moved to {event.dest_path}!")

def runMonitor(observers : list[Watcher] = None):
    notifyMessage("Running Monitor...")

    for o in observers:
        o.run()
        print(f"Monitoring {o.sourcePath}");
    try:
        input()
    except KeyboardInterrupt:
        print(APPLICATION_NAME + " monitoring is interrupted")

""" Ensure Backuped """

import shutil
import filecmp

def tryCopy2(src, dst, excludes : list[str], follow_symlinks=True):
    try:
        if path.exists(dst):
            if filecmp.cmp(src, dst):
                return
            else:
                os.remove(dst)
        shutil.copy2(src, dst)
        notifyMessage(f"Copied '{src}' to '{dst}'")

    except OSError as e:
        raiseWarning(e, COPY_FILES)

def arrangeIgnorePatterns(include : Include) -> list[str]:
    # patterns = []
    # for exclude in include.excludes:
    #     for includeSrc in include.includePaths:
    #         if exclude.startswith(includeSrc):
    #             excludePathTail = exclude.removeprefix(includeSrc + os.sep)
    #             patterns.append(
    #                 excludePathTail #if os.path.isfile(includeSrc) else os.path.join(excludePathTail, '*.*')
    #                 )
    # return patterns
    return [
            exclude.removeprefix(includeSrc + os.sep)
            for exclude in include.excludes 
            for includeSrc in include.includePaths 
            if exclude.startswith(includeSrc)
        ]

def backupSinglePath(observers, include, ignorePatterns, sourcePath):
    try:
        ignore = shutil.ignore_patterns(*ignorePatterns)
        _, sourceFolderName = path.split(sourcePath)
        targetPath = path.join(include.targetPath, sourceFolderName)
        shutil.copytree(
                    sourcePath, targetPath, 
                    dirs_exist_ok=True, 
                    ignore=ignore,
                    copy_function=lambda src, dst: tryCopy2(src, dst, include.excludes)
                    )
        if observers != None:
            o = Watcher(sourcePath, targetPath)
            o.configureObserver(ignorePatterns)
            observers.append(o)
    except OSError as osErr:
        raiseError(str(osErr), FS_ERROR)


def ensureDataIsBackuped(config : Configuration, observers : list[Watcher] = None):
    """If observers is None, don't monitor the file system"""

    for include in config.includes:
        ignorePatterns = arrangeIgnorePatterns(include)
        for sourcePath in include.includePaths:
            backupSinglePath(observers, include, ignorePatterns, sourcePath)

""" 
        Main 
"""
def main():
    print(TITLE)

    try:
        # currentPath = os.path.dirname()
        # address = os.join(currentPath, fileName)
        global logFile
        logFile = open("events.log", "w")
        path = os.path.realpath(__file__)
        log('Started from: ' + path)

        #command = "python " + path
        #_, tail = os.path.split(path)
        #registryKeyName = tail.split(".")[0]
        #print(f"Trying to add to registry key '{registryKeyName}' for '{path}'")

        tryAddToRegistry(path, APPLICATION_NAME)
        config = tryReadConfig()
        config.accept(ConfigurationValidationVisitor())
        printConfiguration(config)
        observers = []
        ensureDataIsBackuped(config, observers)
        runMonitor(observers)

    except Exception as anyError:
        print(anyError)
        input()
    finally:
        logFile.close()

if __name__ == "__main__":
    main()

