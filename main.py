
from __future__ import annotations
from abc import abstractmethod
from multiprocessing.context import Process
from platform import system
import threading
from typing import Any, AnyStr, Callable, Deque, Generic, Iterator, List, Set, Tuple, Type, TypeVar, overload
from dataclasses import dataclass

APPLICATION_NAME = "fi-supporter"
APP_VERSION = "0.1"
TITLE = APPLICATION_NAME.capitalize() + f" version {APP_VERSION}\n"

""" Registry Manipulations"""

from io import TextIOWrapper
import winreg as reg
import os

currentUserKey = reg.HKEY_CURRENT_USER
allUsersKey = reg.HKEY_LOCAL_MACHINE
keyValue = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"


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

INVALID_CONFIG_CAT = "Invalid configuration"
COPY_FILES_CAT = "Unable to copy"
FS_ERROR_CAT = "File system access"
MONITOR_CAT = "Monitor changes reflection"
ATTEMPT_OPERATION_CAT = "Attempt execute operation"
DEVICE_MONITORING_CAT = "Device monitoring"

NO_INCLUDE_PATHS_ERROR = "You have not specified any valid include paths"

logFile : TextIOWrapper

def log(msg : str):
    if not msg.endswith(os.linesep):
        msg += os.linesep
    logFile.writelines(msg)

def notifyMessage(message : str | Exception, end=os.linesep):
    message = str(message)
    print(message, end=end)
    log(message)

def notifyEvent(message : str, category : str, type : str):
    msg = f"{type}: {category}. {message}{os.linesep}"
    notifyMessage(msg, end='')

def raiseError(message : str, category : str):
    notifyEvent(message, category, ERROR)
    raise Exception(message)

def raiseWarning(message : str, category : str):
    notifyEvent(message, category, WARNING)

def pathIfExists(filePath : str) -> str | None:
    if filePath and path.exists(filePath):
        return filePath
    else:
        raiseWarning(f"Can't find the path '{filePath}'", INVALID_CONFIG_CAT)
        return None

def existentPaths(paths : list[str]) -> Iterator[str]:
    for p in paths:
        existentPath = pathIfExists(p)
        if existentPath:
            yield path.abspath(str(existentPath))


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, o : Any) -> Any:
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
    isActive : bool
    includePaths : list[str]
    targetPath : str
    excludes : list[str]

    def __init__(self, includes : list[str], targetPath : str, excludes : list[str]) -> None:
        self.isActive = True
        self.includePaths = includes
        self.targetPath = targetPath
        self.excludes = excludes

    @staticmethod
    def fromObject(obj : dict) -> Include:
        pathsObj : list[str] = obj.get(PATHS) 
        paths : list[str] = list(pathsObj)
        if not paths or not len(paths):
            raiseError(NO_INCLUDE_PATHS_ERROR, INVALID_CONFIG_CAT)
        
        paths = list(existentPaths(paths))

        if not len(paths):
            raiseError(NO_INCLUDE_PATHS_ERROR, INVALID_CONFIG_CAT)
        
        targetPath = path.abspath(str(obj.get(TARGET_PATH)))

        if not targetPath:
            raiseError(f"'{TARGET_PATH}' is unspecified", INVALID_CONFIG_CAT)

        # isActive = True
        # if not path.exists(targetPath):
        #     isActive = False
        #     raiseWarning(f"'{TARGET_PATH}' does not exist, therefore this rule is ignored. Once this target path '{targetPath}' appears in file system the corresponding rule will be activated.", INCORRECT_CONFIG_CAT)
        
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
        if includesObj and len(includesObj):
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
        if includes and len(includes):
            return Configuration(includes)
        else:
            raiseError("No includes specified", INVALID_CONFIG_CAT)

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

def tryReadConfig(appFolder : str) -> Configuration :
    try:
        configFile = os.path.join(appFolder, configFileName)
        print("Configuration path: ", configFile)
        if path.exists(configFile):
            with open(configFile, 'r') as configFile:
                return Configuration.fromFile(configFile)
        else:
            with open(configFile, 'w') as configFile:
                configFile.write(configTemplate)
                raiseError("Created config. Modify the configuration file and restart the application after that", INVALID_CONFIG_CAT)
    except OSError as osErr:
        raiseError(str(osErr), FS_ERROR_CAT)


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
        # Check whether exclude paths are subpaths of include paths:
        isSub = False
        for includePath in self.parentInclude.includePaths:
            if exclude.startswith(includePath):
                isSub = True
        if not isSub:
            raiseWarning(f'Exclude path "{exclude}" is not a subfolder of any "{self.parentInclude.includePaths}"', INVALID_CONFIG_CAT)
            self.parentInclude.excludes.remove(exclude)
        super().visitExclude(exclude)

class ConfigurationUpdateActiveDrivesVisitor(ConfigurationVisitor):

    activatedRules : list[Include]
    deactivatedRules : list[Include]

    def __init__(self) -> None:
        self.activatedRules = []
        self.deactivatedRules = []
        super().__init__()

    def visitInclude(self, include: Include) -> None:
        wasActive = include.isActive
        drive, _ = os.path.splitdrive(include.targetPath)
        include.isActive = os.path.exists(drive)
        if wasActive ^ include.isActive:
            if include.isActive:
                self.activatedRules.append(include)
                notifyMessage(f"Rule for target path: '{include.targetPath}' is activated")
            else:
                self.deactivatedRules.append(include)
                notifyMessage(f"Rule for target path: '{include.targetPath}' is deactivated because the drive '{drive}' does not exists. Once the device is plugged in, the corresponding rule will be activated.")
        return super().visitInclude(include)

""" Periodical attempts to execute unsuccessful synchronizions """

import datetime
from threading import Timer

# class classproperty(property):
#     def __get__(self, __cls: Any, __owner) -> Any:
#         if self.fget == None:
#             return None
#         else:
#             return classmethod(self.fget).__get__(None, __owner)()

class AttemptOperation:
    operation : Callable[[], None]

    def __init__(self, operation : Callable[[], None]) -> None:
        self.operation = operation

    def tryExecute(self) -> bool:
        try:
            self.operation()
            return True
        except Exception as ex:
            notifyEvent(str(ex), ATTEMPT_OPERATION_CAT, ERROR)
            return False

class AttemptsManager:
    _timer : Timer | None;
    _period : float
    _operations : list[AttemptOperation]
    _hasStarted : bool

    def __init__(self, time_delta : datetime.timedelta = datetime.timedelta(minutes=1)) -> None:
        self._period = time_delta.seconds
        self._operations = []
        self._hasStarted = False
        self._timer = None
        self.reset_timer()

    def reset_timer(self) -> Timer:
        if self._timer == None:
            self._timer = Timer(self._period, self.inquire)
        self._timer.name = self.__class__.__name__
        self._timer.daemon = True
        return self._timer

    def QueueOperation(self, operation : AttemptOperation):
        if self._hasStarted:
            self.stop()
            self._operations.append(operation)
            self.start()
        else:
            self._operations.append(operation)
    
    def QueueCallable(self, callback : Callable[[], None], msg : str = "Operation has been queued"):
        notifyMessage(msg)
        self.QueueOperation(AttemptOperation(callback))

    def Dequeue(self, operations : list[AttemptOperation]):
        if self._hasStarted:
            self.stop()
            for op in operations:
                self._operations.remove(op)
            self.start()
        else:
            for op in operations:
                self._operations.remove(op)

    def start(self):
        self._hasStarted = True
        self.reset_timer().start()

    def stop(self):
        self._hasStarted = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def inquire(self):
        operationsToRemove : list[AttemptOperation] = []
        for op in self._operations:
            if op.tryExecute():
                operationsToRemove.append(op)
        if len(operationsToRemove):
            self.Dequeue(operationsToRemove)

        self.stop()
        if len(self._operations):
            self.start()

attemptsManager : AttemptsManager= AttemptsManager()

""" Setup file system monitoring """

import shutil
import filecmp

from watchdog.observers import Observer
from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent, PatternMatchingEventHandler
from watchdog.utils import patterns

def ensureParentFolderExists(dst : str):
    folder, _ = os.path.split(dst)
    if not os.path.exists(folder):
        ensureParentFolderExists(folder)
        os.mkdir(folder)

def CopyMethod(src, dst):
    ensureParentFolderExists(dst)
    return shutil.copy2(src, dst)

class Watcher:
    sourcePath : str
    baseTargetPath : str
    sourceFolderName : str
    ignorePaths : list[str]
    observer : Observer
    handler : FileSystemEventHandler

    def __init__(self, src : str, baseTargetPath : str, sourceFolderName : str) -> None:
        self.sourcePath = src
        self.baseTargetPath = baseTargetPath
        self.sourceFolderName = sourceFolderName
        self.observer = Observer()
    
    def configureObserver(self, ignorePatterns : Any = []):
        self.ignorePaths = ignorePatterns
        _, file_name = os.path.split(self.sourcePath)
        self.observer.name = f'observer-{file_name}'
        self.handler = PatternMatchingEventHandler(
            "*", ignorePatterns, ignore_directories=False, case_sensitive=True)
        self.handler.on_created = self.on_created
        self.handler.on_deleted = self.on_deleted
        self.handler.on_modified = self.on_modified
        self.handler.on_moved = self.on_moved
    
    def run(self):
        if self.handler == None:
            self.configureObserver()
        try:
            self.observer.schedule(self.handler, self.sourcePath, recursive=True)
            self.observer.start()
        except Exception as ex:
            raise ex

    def stop(self):
        self.observer.stop()
        self.observer.join()

    def shouldIgnore(self, path : str) -> bool:
        for ignorePath in self.ignorePaths: 
            if path.startswith(os.path.join(self.sourcePath, ignorePath)):
                return True
        return False

    @property
    def targetPath(self):
        return os.path.join(self.baseTargetPath, self.sourceFolderName)

    def destinationPath(self, fromPath : str):
        tailSubpath = fromPath.removeprefix(self.sourcePath).removeprefix(os.sep)
        return path.join(self.targetPath, tailSubpath)
    
    def copyItem(self, srcPath : str) -> str:
        destination = self.destinationPath(srcPath)
        return CopyMethod(srcPath, destination)
    
    def _create(self, srcPath):
        if os.path.isfile(srcPath):
            destination = self.copyItem(srcPath)
            notifyMessage(f"{destination} has been created!")
    
    def on_created(self, event : FileSystemEvent):
        srcPath = str(event.src_path)
        if self.shouldIgnore(srcPath):
            return
        try:
            self._create(srcPath)
        except PermissionError as permissionErr:
            attemptsManager.QueueCallable(lambda : self._create(srcPath), f"Deletion of {self.destinationPath(srcPath)} operation has been queued")
            attemptsManager.start()
        except OSError as osErr:
            notifyEvent(str(osErr), MONITOR_CAT, ERROR)

    def _delete(self, destination):
        if os.path.isfile(destination):
            os.remove(destination)
        else:
            shutil.rmtree(destination)
        notifyMessage(f"{destination} has been deleted!")
    
    def on_deleted(self, event : FileSystemEvent):
        srcPath = str(event.src_path)
        if self.shouldIgnore(srcPath):
            return
        destination = self.destinationPath(srcPath)
        try:
            self._delete(destination)
        except PermissionError as permissionErr:
            attemptsManager.QueueCallable(lambda : self._delete(destination), f"Deletion of {self.destinationPath(destination)} operation has been queued")
            attemptsManager.start()
        except OSError as osErr:
            notifyEvent(str(osErr), MONITOR_CAT, ERROR)

    def _replace(self, srcPath):
        if os.path.isfile(srcPath):
            dst = self.destinationPath(srcPath)
            if not os.path.exists(dst) or not filecmp.cmp(srcPath, dst):
                destination = CopyMethod(srcPath, dst)
                notifyMessage(f"{destination} has been replaced!")
    
    def on_modified(self, event : FileSystemEvent):
        srcPath = str(event.src_path)
        if self.shouldIgnore(srcPath):
            return
        try:
            self._replace(srcPath)
        except PermissionError as permissionErr:
            attemptsManager.QueueCallable(lambda : self._replace(srcPath), f"Replace of {self.destinationPath(srcPath)} operation has been queued")
            attemptsManager.start()
        except OSError as osErr:
            notifyEvent(str(osErr), MONITOR_CAT, ERROR)

    def nameIsDifferent(self, srcPath, destPath) -> bool:
        _,srcName = os.path.split(srcPath)
        _,dstName = os.path.split(destPath)
        return srcName != dstName

    def on_moved(self, event : FileSystemMovedEvent):
        srcPath = str(event.src_path)
        if self.shouldIgnore(srcPath):
            return
        targetSourcePath = self.destinationPath(srcPath) 
        destPath = str(event.dest_path)
        targetDestPath = self.destinationPath(destPath)

        if path.exists(targetSourcePath) and self.nameIsDifferent(srcPath, destPath):
            try:
                self._rename(targetSourcePath, targetDestPath)
            except PermissionError as permissionErr:
                attemptsManager.QueueCallable(lambda : self._rename(targetSourcePath, targetDestPath), f"Rename of {targetSourcePath} operation has been queued")
                attemptsManager.start()
            except OSError as osErr:
                notifyEvent(str(osErr), MONITOR_CAT, ERROR)

    def _rename(self, targetSourcePath, targetDestPath):
        if os.path.exists(targetDestPath):
            self._delete(targetDestPath)
        os.rename(targetSourcePath, targetDestPath)
        notifyMessage(f"{targetSourcePath} has been moved to {targetDestPath}!")

def observeFileSystem(observers : list[Watcher] = None):
    if observers:
        for o in observers:
            o.run()
            print(f"Monitoring '{o.sourcePath}'")

""" Ensure Backuped """

def tryCopy2(src, dst, excludes : list[str], follow_symlinks=True):
    try:
        if path.exists(dst):
            if filecmp.cmp(src, dst):
                return
            else:
                os.remove(dst)
        CopyMethod(src, dst)
        notifyMessage(f"Copied '{src}' to '{dst}'")
    except OSError as e:
        raiseWarning(str(e), COPY_FILES_CAT)

def arrangeIgnorePatterns(include : Include) -> list[str]:
    return [
            exclude.removeprefix(includeSrc + os.sep)
            for exclude in include.excludes 
            for includeSrc in include.includePaths 
            if exclude.startswith(includeSrc)
        ]

def backupSinglePath(observers : list[Watcher] | None, include : Include, ignorePatterns : list[str], sourcePath : str):
    try:
        ignore = shutil.ignore_patterns(*ignorePatterns)
        sourceFolderName = os.path.basename(sourcePath)
        targetPath = path.join(include.targetPath, sourceFolderName)
        shutil.copytree(
                    sourcePath, targetPath, 
                    dirs_exist_ok=True, 
                    ignore=ignore,
                    copy_function=lambda src, dst: tryCopy2(src, dst, include.excludes)
                    )
        if observers != None:
            o = Watcher(sourcePath, include.targetPath, sourceFolderName)
            o.configureObserver(ignorePatterns)
            observers.append(o)
    except OSError as osErr:
        raiseError(str(osErr), FS_ERROR_CAT)

def ensureDataIsBackuped(includes: list[Include], observers : list[Watcher] = None):
    """If observers is None, don't monitor the file system"""
    for include in includes:
        ignorePatterns = arrangeIgnorePatterns(include)
        for sourcePath in include.includePaths:
            if include.isActive:
                backupSinglePath(observers, include, ignorePatterns, sourcePath)
            #else:
            #    notifyMessage(f"Rule for destination path '{include.targetPath}' is deactivated")

""" Device Monitoring """

import atexit
import subprocess
from threading import Thread, Timer

try:
    import win32api, win32con, win32gui
except:
    os.system('pip install pywin32')
    import win32api, win32con, win32gui

@dataclass
class Drive:
    letter : str
    label : str
    type : str

    def __init__(self, letter : str, label : str, type : str) -> None:
        self.letter = letter
        self.label = label
        self.type = type

    def __repr__(self) -> str:
        return f"{(self.letter, self.label, self.type)}"

    def __hash__(self) -> int:
        return self.letter.__hash__()
    
    @staticmethod
    def fromJson(values):
        return Drive(values['deviceid'], values['volumename'], values['drivetype'])

class DeviceListener:
    WM_DEVICECHANGE_EVENTS = {
        0x0019: ('DBT_CONFIGCHANGECANCELED', 'A request to change the current configuration (dock or undock) has been canceled.'),
        0x0018: ('DBT_CONFIGCHANGED', 'The current configuration has changed, due to a dock or undock.'),
        0x8006: ('DBT_CUSTOMEVENT', 'A custom event has occurred.'),
        0x8000: ('DBT_DEVICEARRIVAL', 'A device or piece of media has been inserted and is now available.'),
        0x8001: ('DBT_DEVICEQUERYREMOVE', 'Permission is requested to remove a device or piece of media. Any application can deny this request and cancel the removal.'),
        0x8002: ('DBT_DEVICEQUERYREMOVEFAILED', 'A request to remove a device or piece of media has been canceled.'),
        0x8004: ('DBT_DEVICEREMOVECOMPLETE', 'A device or piece of media has been removed.'),
        0x8003: ('DBT_DEVICEREMOVEPENDING', 'A device or piece of media is about to be removed. Cannot be denied.'),
        0x8005: ('DBT_DEVICETYPESPECIFIC', 'A device-specific event has occurred.'),
        0x0007: ('DBT_DEVNODES_CHANGED', 'A device has been added to or removed from the system.'),
        0x0017: ('DBT_QUERYCHANGECONFIG', 'Permission is requested to change the current configuration (dock or undock).'),
        0xFFFF: ('DBT_USERDEFINED', 'The meaning of this message is user-defined.'),
    }

    onDrivesChangedHandler : Callable[[], None]

    def __init__(self, drivesChangedCallback : Callable[[], None]) -> None:
        self.onDrivesChangedHandler = drivesChangedCallback

    def _on_message(self, hwnd : int, msg : int, wparam : int, lparam : int):
        if msg != win32con.WM_DEVICECHANGE:
            return 0
        event, description = self.WM_DEVICECHANGE_EVENTS[wparam]
        if event in ('DBT_DEVNODES_CHANGED', 'DBT_DEVICEREMOVECOMPLETE', 'DBT_DEVICEARRIVAL'):
            self.onDrivesChangedHandler()
        return 0
    
    def _create_window(self):
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._on_message
        wc.lpszClassName = self.__class__.__name__
        wc.hInstance = win32api.GetModuleHandle()
        class_atom = win32gui.RegisterClass(wc)
        return win32gui.CreateWindow(class_atom, self.__class__.__name__, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)

    def run(self):
        hwmd = self._create_window()
        win32gui.PumpMessages()

class DevicesWatcher:

    _deviceListener : DeviceListener
    _configuration : Configuration
    _onActivate : Callable[[list[Include]], None]
    _onDeactivate : Callable[[list[Include]], None]

    def __init__(self, config : Configuration, activation : Callable[[list[Include]], None], deactivate : Callable[[list[Include]], None]) -> None:
        self._configuration = config
        self._onActivate = activation
        self._onDeactivate = deactivate
        self._deviceListener = DeviceListener(self.devicesChanged)

    def run(self):
        self._deviceListener.run()

    def devicesChanged(self):
        activeDrivesVisitor = ConfigurationUpdateActiveDrivesVisitor()
        self._configuration.accept(activeDrivesVisitor)
        if self._onActivate and len(activeDrivesVisitor.activatedRules):
            self._onActivate(activeDrivesVisitor.activatedRules)
        if self._onDeactivate and len(activeDrivesVisitor.deactivatedRules):
            self._onDeactivate(activeDrivesVisitor.deactivatedRules)

        #availableDrives = DevicesWatcher.listDrives()
        #drivesIntersection = set(availableDrives).intersection(self._drivesToWatch)
        #print(f"Drives updated:\n{list[drivesIntersection]}")

    @staticmethod
    def listDrives() -> list[Drive] | None:
        proc = subprocess.run(args=[
                'powershell',
                '-noprofile',
                '-command',
                'Get-WmiObject -Class Win32_LogicalDisk | Select-Object deviceid,volumename,drivetype | ConvertTo-Json'
            ],
            text=True,
            stdout=subprocess.PIPE)
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        drives = json.loads(proc.stdout)
        if type(drives).__name__ == 'dict':
            return [Drive.fromJson(drives)]
        elif type(drives).__name__ == 'list': 
            return [Drive.fromJson(drive) for drive in drives]
        else:
            raise Exception()

def activateRules(includes : list[Include], watchers : list[Watcher]):
    """New includes that were activated; working observers"""
    if includes == None or len(includes) == 0:
        return

    addedObservers = []
    ensureDataIsBackuped(includes, addedObservers)
    if len(addedObservers) > 0:
        observeFileSystem(addedObservers)
        watchers.extend(addedObservers)


def deactivateRules(deactivatedIncludes : list[Include], watchers : list[Watcher]):
    """New includes that were deactivated; working observers"""
    if deactivatedIncludes == None or len(deactivatedIncludes) == 0:
        return
    
    watchersClone = watchers[:]
    for include in deactivatedIncludes:
        for watcher in watchersClone:
            if watcher.baseTargetPath == include.targetPath and watcher.sourcePath in include.includePaths:
                watcher.stop()
                watchers.remove(watcher)

def runDeviceWatcher(config, watchers) -> Thread | None:
    try:
        devicesWatcher = DevicesWatcher(config, 
                        lambda rules: activateRules(rules, watchers), 
                        lambda rules: deactivateRules(rules, watchers))
        
        devWatcher = threading.Thread(target=devicesWatcher.run, name="device-watcher")
        devWatcher.daemon = True
        devWatcher.start()
        return devWatcher
        
    except Exception as ex:
        notifyMessage(str(ex), DEVICE_MONITORING_CAT)
        return None


def main():
    print(TITLE)

    # attemptsManager : AttemptsManager = AttemptsManager(datetime.timedelta(seconds=6))
    # attemptsManager.QueueOperation(AttemptOperation(lambda: print("Attempt #1")))
    # def f():
    #     print("Attempt #2"); 
    #     raise Exception("Exception")
    # attemptsManager.QueueOperation(AttemptOperation(f))
    # attemptsManager.QueueOperation(AttemptOperation(lambda: print("Attempt #3")))
    # attemptsManager.start()
    # input()

    try:
        # currentPath = os.path.dirname()
        # address = os.join(currentPath, fileName)
        global logFile
        logFile = open("events.log", "w")
        path = os.path.realpath(__file__)
        notifyMessage('Started from: ' + path)

        #command = "python " + path
        #_, tail = os.path.split(path)
        #registryKeyName = tail.split(".")[0]
        #print(f"Trying to add to registry key '{registryKeyName}' for '{path}'")

        tryAddToRegistry(path, APPLICATION_NAME)
        currentFolder, _ = os.path.split(__file__)
        config = tryReadConfig(currentFolder)
        config.accept(ConfigurationValidationVisitor())
        activeDrivesVisitor = ConfigurationUpdateActiveDrivesVisitor()
        config.accept(activeDrivesVisitor)
        #printConfiguration(config)
        watchers = []
        ensureDataIsBackuped(config.includes, watchers)
        
        notifyMessage("Running Monitor...")
        observeFileSystem(watchers)

        runDeviceWatcher(config, watchers)

        try:
            while True:
                input()
        except KeyboardInterrupt:
            print(APPLICATION_NAME + " monitoring is interrupted")

    except Exception as anyError:
        notifyMessage(anyError)
        input()

def onExitHandler():
    print('<exited>')
    logFile.close()

if __name__ == "__main__":
    atexit.register(onExitHandler)
    main()

