
from __future__ import annotations
from abc import abstractmethod
from typing import Any, Callable, Iterator
from dataclasses import dataclass

import threading

APPLICATION_NAME = "fi-supporter"
APP_VERSION = "0.1"
TITLE = APPLICATION_NAME.capitalize() + f" version {APP_VERSION}\n"

""" Registry Manipulations"""

from io import TextIOWrapper
import winreg as reg
import os

current_user_key = reg.HKEY_CURRENT_USER
all_users_key = reg.HKEY_LOCAL_MACHINE
key_value = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"

def set_registry_key(path, reg_key_name, open):
    reg.SetValueEx(open, reg_key_name, 0, reg.REG_SZ, path)

def try_add_to_registry(path : str, reg_key_name : str, all_users : bool = False):
    
    key_category = (all_users_key if all_users else current_user_key)
    key_type = reg.ConnectRegistry(None, key_category)
    open = reg.OpenKey(key_type, key_value, 0, reg.KEY_ALL_ACCESS)
    try:
        value, type = reg.QueryValueEx(open, reg_key_name)
        if not (type == reg.REG_SZ and value == path):
            set_registry_key(path, reg_key_name, open)
    except FileNotFoundError:
        set_registry_key(path, reg_key_name, open)
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

log_file : TextIOWrapper

def log(msg : str):
    if not msg.endswith(os.linesep):
        msg += os.linesep
    log_file.writelines(msg)

def notify_message(message : str | Exception, end=os.linesep):
    message = str(message)
    print(message, end=end)
    log(message)

def notify_event(message : str, category : str, type : str):
    msg = f"{type}: {category}. {message}{os.linesep}"
    notify_message(msg, end='')

def raise_error(message : str, category : str):
    notify_event(message, category, ERROR)
    raise Exception(message)

def raise_warning(message : str, category : str):
    notify_event(message, category, WARNING)

def get_path_if_exists(file_path : str) -> str | None:
    if file_path and path.exists(file_path):
        return file_path
    else:
        raise_warning(f"Can't find the path '{file_path}'", INVALID_CONFIG_CAT)
        return None

def get_existent_paths(paths : list[str]) -> Iterator[str]:
    for one_path in paths:
        existent_path = get_path_if_exists(one_path)
        if existent_path:
            yield path.abspath(str(existent_path))


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, o : Any) -> Any:
        if type(o).__name__ == 'Configuration' or type(o).__name__ == 'Include' or type(o).__name__ == 'Exclude':
            return o.__dict__
        else:
            return json.JSONEncoder.default(self, o)

def print_configuration(config):
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

class Include(ConfigurationRule):
    is_active : bool
    include_paths : list[str]
    target_path : str
    excludes : list[str]

    def __init__(self, includes : list[str], target_path : str, excludes : list[str]) -> None:
        self.is_active = True
        self.include_paths = includes
        self.target_path = target_path
        self.excludes = excludes

    @staticmethod
    def from_object(obj : dict) -> Include:
        paths_obj : list[str] = obj.get(PATHS) 
        paths : list[str] = list(paths_obj)
        if not paths or not len(paths):
            raise_error(NO_INCLUDE_PATHS_ERROR, INVALID_CONFIG_CAT)
        
        paths = list(get_existent_paths(paths))

        if not len(paths):
            raise_error(NO_INCLUDE_PATHS_ERROR, INVALID_CONFIG_CAT)
        
        target_path = path.abspath(str(obj.get(TARGET_PATH)))

        if not target_path:
            raise_error(f"'{TARGET_PATH}' is unspecified", INVALID_CONFIG_CAT)
        
        excludes = obj.get(EXCLUDES)
        if excludes and len(excludes):
            excludes = list(get_existent_paths(excludes))
        else:
            excludes = []

        return Include(paths, target_path, excludes)
    
    def accept(self, visitor : ConfigurationVisitor):
        visitor.visit_include(self)
        if self.excludes:
            for exclude in list(self.excludes):
                visitor.visit_exclude(exclude)
    
    def __repr__(self) -> str:
        return str(self.__dict__)

class Configuration(ConfigurationRule):

    includes : list[Include]
    
    def __init__(self, includes : list[Include]):
        self.includes = includes
    
    @staticmethod
    def parse_includes(obj : dict) -> list[Include] | None:
        includes_obj = obj.get(INCLUDES)
        if includes_obj and len(includes_obj):
            includes : list[Include] = list();
            for include_obj in includes_obj:
                if include_obj:
                    include = Include.from_object(include_obj)
                    if include:
                        includes.append(include)
            if (len(includes)):
                return includes
        return None

    @staticmethod
    def from_object(obj : dict) -> Configuration:
        includes = Configuration.parse_includes(obj)
        if includes and len(includes):
            return Configuration(includes)
        else:
            raise_error("No includes specified", INVALID_CONFIG_CAT)

    @staticmethod
    def from_string(contents : str) -> Configuration:
        return Configuration.from_object(json.loads(contents))

    @staticmethod
    def from_file(fi : TextIOWrapper) -> Configuration:
        return Configuration.from_string(fi.read())

    def accept(self, visitor : ConfigurationVisitor):
        visitor.visit_configuration(self)
        for include in self.includes:
            include.accept(visitor)

    def __repr__(self) -> str:
        return str(self.__dict__)
    

CONFIG_FILE_NAME = "config.json"
CONFIG_TEMPLATE = """{
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

def try_read_config(appFolder : str) -> Configuration :
    try:
        config_file = os.path.join(appFolder, CONFIG_FILE_NAME)
        print("Configuration path: ", config_file)
        if path.exists(config_file):
            with open(config_file, 'r') as config_file:
                return Configuration.from_file(config_file)
        else:
            with open(config_file, 'w') as config_file:
                config_file.write(CONFIG_TEMPLATE)
                raise_error("Created config. Modify the configuration file and restart the application after that", INVALID_CONFIG_CAT)
    except OSError as osErr:
        raise_error(str(osErr), FS_ERROR_CAT)


""" Configuration Manipulations """

class ConfigurationVisitor:
    @abstractmethod
    def visit_configuration(self, config : Configuration) -> None:
        pass
    
    @abstractmethod
    def visit_include(self, include : Include) -> None:
        pass

    @abstractmethod
    def visit_exclude(self, exclude : str) -> None:
        pass

class ConfigurationValidationVisitor(ConfigurationVisitor):
    parent_include : Include

    def __init__(self) -> None:
        super().__init__()

    def visit_configuration(self, config : Configuration) -> None:
        super().visit_configuration(config)
    
    def visit_include(self, include : Include) -> None:
        self.parent_include = include
        super().visit_include(include)
    
    def visit_exclude(self, exclude : str) -> None:
        # Check whether exclude paths are subpaths of include paths:
        is_sub = False
        for include_path in self.parent_include.include_paths:
            if exclude.startswith(include_path):
                is_sub = True
        if not is_sub:
            raise_warning(f'Exclude path "{exclude}" is not a subfolder of any "{self.parent_include.include_paths}"', INVALID_CONFIG_CAT)
            self.parent_include.excludes.remove(exclude)
        super().visit_exclude(exclude)

class ConfigurationUpdateActiveDrivesVisitor(ConfigurationVisitor):

    activated_rules : list[Include]
    deactivated_rules : list[Include]

    def __init__(self) -> None:
        self.activated_rules = []
        self.deactivated_rules = []
        super().__init__()

    def visit_include(self, include: Include) -> None:
        was_active = include.is_active
        drive, _ = os.path.splitdrive(include.target_path)
        include.is_active = os.path.exists(drive)
        if was_active ^ include.is_active:
            if include.is_active:
                self.activated_rules.append(include)
                notify_message(f"Rule for target path: '{include.target_path}' is activated")
            else:
                self.deactivated_rules.append(include)
                notify_message(f"Rule for target path: '{include.target_path}' is deactivated because the drive '{drive}' does not exists. Once the device is plugged in, the corresponding rule will be activated.")
        return super().visit_include(include)

""" Periodical attempts to execute unsuccessful synchronizions """

from threading import Timer
import datetime

class AttemptOperation:
    operation : Callable[[], None]

    def __init__(self, operation : Callable[[], None]) -> None:
        self.operation = operation

    def try_execute(self) -> bool:
        try:
            self.operation()
            return True
        except Exception as ex:
            notify_event(str(ex), ATTEMPT_OPERATION_CAT, ERROR)
            return False

class AttemptsManager:
    _timer : Timer | None;
    _period : float
    _operations : list[AttemptOperation]
    _has_started : bool

    def __init__(self, time_delta : datetime.timedelta = datetime.timedelta(minutes=1)) -> None:
        self._period = time_delta.seconds
        self._operations = []
        self._has_started = False
        self._timer = None
        self.reset_timer()

    def reset_timer(self) -> Timer:
        if self._timer == None:
            self._timer = Timer(self._period, self.inquire)
        self._timer.name = self.__class__.__name__
        self._timer.daemon = True
        return self._timer

    def queue_operation(self, operation : AttemptOperation):
        if self._has_started:
            self.stop()
            self._operations.append(operation)
            self.start()
        else:
            self._operations.append(operation)
    
    def queue_callable(self, callback : Callable[[], None], msg : str = "Operation has been queued"):
        notify_message(msg)
        self.queue_operation(AttemptOperation(callback))

    def dequeue(self, operations : list[AttemptOperation]):
        if self._has_started:
            self.stop()
            for op in operations:
                self._operations.remove(op)
            self.start()
        else:
            for op in operations:
                self._operations.remove(op)

    def start(self):
        self._has_started = True
        self.reset_timer().start()

    def stop(self):
        self._has_started = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def inquire(self):
        operations_to_remove : list[AttemptOperation] = []
        for op in self._operations:
            if op.try_execute():
                operations_to_remove.append(op)
        if len(operations_to_remove):
            self.dequeue(operations_to_remove)

        self.stop()
        if len(self._operations):
            self.start()

attempts_manager : AttemptsManager = AttemptsManager()

""" Setup file system monitoring """

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent, PatternMatchingEventHandler
except:
    os.system('pip install watchdog')
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEvent, FileSystemEventHandler, FileSystemMovedEvent, PatternMatchingEventHandler

import shutil
import filecmp

def ensure_parent_folder_exists(dst : str):
    folder, _ = os.path.split(dst)
    if not os.path.exists(folder):
        ensure_parent_folder_exists(folder)
        os.mkdir(folder)

def copy_method(src, dst):
    ensure_parent_folder_exists(dst)
    return shutil.copy2(src, dst)

class Watcher:
    source_path : str
    base_target_path : str
    source_folder_name : str
    ignore_paths : list[str]
    observer : Observer
    handler : FileSystemEventHandler

    def __init__(self, src : str, base_target_path : str, source_folder_name : str) -> None:
        self.source_path = src
        self.base_target_path = base_target_path
        self.source_folder_name = source_folder_name
        self.observer = Observer()
    
    def configure_observer(self, ignore_patterns : Any = []):
        self.ignore_paths = ignore_patterns
        _, file_name = os.path.split(self.source_path)
        self.observer.name = f'observer-{file_name}'
        self.handler = PatternMatchingEventHandler(
            "*", ignore_patterns, ignore_directories=False, case_sensitive=True)
        self.handler.on_created = self.on_created
        self.handler.on_deleted = self.on_deleted
        self.handler.on_modified = self.on_modified
        self.handler.on_moved = self.on_moved
    
    def run(self):
        if self.handler == None:
            self.configure_observer()
        try:
            self.observer.schedule(self.handler, self.source_path, recursive=True)
            self.observer.start()
        except Exception as ex:
            raise ex

    def stop(self):
        self.observer.stop()
        self.observer.join()

    def _should_ignore(self, path : str) -> bool:
        for ignore_path in self.ignore_paths: 
            if path.startswith(os.path.join(self.source_path, ignore_path)):
                return True
        return False

    @property
    def target_path(self):
        return os.path.join(self.base_target_path, self.source_folder_name)

    def _destination_path(self, from_path : str):
        tail_subpath = from_path.removeprefix(self.source_path).removeprefix(os.sep)
        return path.join(self.target_path, tail_subpath)
    
    def _copy_item(self, src_path : str) -> str:
        destination = self._destination_path(src_path)
        return copy_method(src_path, destination)
    
    def _create(self, src_path):
        if os.path.isfile(src_path):
            destination = self._copy_item(src_path)
            notify_message(f"{destination} has been created!")
    
    def on_created(self, event : FileSystemEvent):
        src_path = str(event.src_path)
        if self._should_ignore(src_path):
            return
        try:
            self._create(src_path)
        except PermissionError as permissionErr:
            attempts_manager.queue_callable(lambda : self._create(src_path), f"Deletion of {self._destination_path(src_path)} operation has been queued")
            attempts_manager.start()
        except OSError as os_err:
            notify_event(str(os_err), MONITOR_CAT, ERROR)

    def _delete(self, destination):
        if os.path.isfile(destination):
            os.remove(destination)
        else:
            shutil.rmtree(destination)
        notify_message(f"{destination} has been deleted!")
    
    def on_deleted(self, event : FileSystemEvent):
        src_path = str(event.src_path)
        if self._should_ignore(src_path):
            return
        destination = self._destination_path(src_path)
        try:
            self._delete(destination)
        except PermissionError as permissionErr:
            attempts_manager.queue_callable(lambda : self._delete(destination), f"Deletion of {self._destination_path(destination)} operation has been queued")
            attempts_manager.start()
        except OSError as os_err:
            notify_event(str(os_err), MONITOR_CAT, ERROR)

    def _replace(self, src_path):
        if os.path.isfile(src_path):
            dst = self._destination_path(src_path)
            if not os.path.exists(dst) or not filecmp.cmp(src_path, dst):
                destination = copy_method(src_path, dst)
                notify_message(f"{destination} has been replaced!")
    
    def on_modified(self, event : FileSystemEvent):
        src_path = str(event.src_path)
        if self._should_ignore(src_path):
            return
        try:
            self._replace(src_path)
        except PermissionError as permission_err:
            attempts_manager.queue_callable(lambda : self._replace(src_path), f"Replace of {self._destination_path(src_path)} operation has been queued")
            attempts_manager.start()
        except OSError as os_err:
            notify_event(str(os_err), MONITOR_CAT, ERROR)

    def nameIsDifferent(self, src_path, dest_path) -> bool:
        _, src_name = os.path.split(src_path)
        _, dst_name = os.path.split(dest_path)
        return src_name != dst_name

    def on_moved(self, event : FileSystemMovedEvent):
        src_path = str(event.src_path)
        if self._should_ignore(src_path):
            return
        target_source_path = self._destination_path(src_path) 
        dest_path = str(event.dest_path)
        target_dest_path = self._destination_path(dest_path)

        if path.exists(target_source_path) and self.nameIsDifferent(src_path, dest_path):
            try:
                self._rename(target_source_path, target_dest_path)
            except PermissionError as permission_err:
                attempts_manager.queue_callable(lambda : self._rename(target_source_path, target_dest_path), f"Rename of {target_source_path} operation has been queued")
                attempts_manager.start()
            except OSError as osErr:
                notify_event(str(osErr), MONITOR_CAT, ERROR)

    def _rename(self, target_source_path, target_dest_path):
        if os.path.exists(target_dest_path):
            self._delete(target_dest_path)
        os.rename(target_source_path, target_dest_path)
        notify_message(f"{target_source_path} has been moved to {target_dest_path}!")

def observe_file_system(observers : list[Watcher] = None):
    if observers:
        for observer in observers:
            observer.run()
            print(f"Monitoring '{observer.source_path}'")

""" Ensure Backuped """

def try_copy2(src, dst, excludes : list[str], follow_symlinks=True):
    try:
        if path.exists(dst):
            if filecmp.cmp(src, dst):
                return
            else:
                os.remove(dst)
        copy_method(src, dst)
        notify_message(f"Copied '{src}' to '{dst}'")
    except OSError as e:
        raise_warning(str(e), COPY_FILES_CAT)

def arrange_ignore_patterns(include : Include) -> list[str]:
    return [
            exclude.removeprefix(include_src + os.sep)
            for exclude in include.excludes 
            for include_src in include.include_paths 
            if exclude.startswith(include_src)
        ]

def backup_single_path(observers : list[Watcher] | None, include : Include, ignore_patterns : list[str], source_path : str):
    try:
        ignore = shutil.ignore_patterns(*ignore_patterns)
        source_folder_name = os.path.basename(source_path)
        target_path = path.join(include.target_path, source_folder_name)
        shutil.copytree(
                    source_path, target_path, 
                    dirs_exist_ok=True, 
                    ignore=ignore,
                    copy_function=lambda src, dst: try_copy2(src, dst, include.excludes)
                    )
        if observers != None:
            observer = Watcher(source_path, include.target_path, source_folder_name)
            observer.configure_observer(ignore_patterns)
            observers.append(observer)
    except OSError as os_err:
        raise_error(str(os_err), FS_ERROR_CAT)

def ensure_data_is_backuped(includes: list[Include], observers : list[Watcher] = None):
    """If observers is None, don't monitor the file system"""
    for include in includes:
        ignore_patterns = arrange_ignore_patterns(include)
        for source_path in include.include_paths:
            if include.is_active:
                backup_single_path(observers, include, ignore_patterns, source_path)

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
    def from_json(values):
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

    on_drives_changed_handler : Callable[[], None]

    def __init__(self, drivesChangedCallback : Callable[[], None]) -> None:
        self.on_drives_changed_handler = drivesChangedCallback

    def _on_message(self, hwnd : int, msg : int, wparam : int, lparam : int):
        if msg != win32con.WM_DEVICECHANGE:
            return 0
        event, description = self.WM_DEVICECHANGE_EVENTS[wparam]
        if event in ('DBT_DEVNODES_CHANGED', 'DBT_DEVICEREMOVECOMPLETE', 'DBT_DEVICEARRIVAL'):
            self.on_drives_changed_handler()
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
    _on_activate : Callable[[list[Include]], None]
    _on_deactivate : Callable[[list[Include]], None]

    def __init__(self, config : Configuration, activation : Callable[[list[Include]], None], deactivate : Callable[[list[Include]], None]) -> None:
        self._configuration = config
        self._on_activate = activation
        self._on_deactivate = deactivate
        self._deviceListener = DeviceListener(self.devices_changed)

    def run(self):
        self._deviceListener.run()

    def devices_changed(self):
        active_drives_visitor = ConfigurationUpdateActiveDrivesVisitor()
        self._configuration.accept(active_drives_visitor)
        if self._on_activate and len(active_drives_visitor.activated_rules):
            self._on_activate(active_drives_visitor.activated_rules)
        if self._on_deactivate and len(active_drives_visitor.deactivated_rules):
            self._on_deactivate(active_drives_visitor.deactivated_rules)

    @staticmethod
    def list_drives() -> list[Drive] | None:
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
            return [Drive.from_json(drives)]
        elif type(drives).__name__ == 'list': 
            return [Drive.from_json(drive) for drive in drives]
        else:
            raise Exception()

def activate_rules(includes : list[Include], watchers : list[Watcher]):
    """New includes that were activated; working observers"""
    if includes == None or len(includes) == 0:
        return

    added_observers = []
    ensure_data_is_backuped(includes, added_observers)
    if len(added_observers) > 0:
        observe_file_system(added_observers)
        watchers.extend(added_observers)


def deactivate_rules(deactivated_includes : list[Include], watchers : list[Watcher]):
    """New includes that were deactivated; working observers"""
    if deactivated_includes == None or len(deactivated_includes) == 0:
        return
    
    watchers_clone = watchers[:]
    for include in deactivated_includes:
        for watcher in watchers_clone:
            if watcher.base_target_path == include.target_path and watcher.source_path in include.include_paths:
                watcher.stop()
                watchers.remove(watcher)

def run_device_watcher(config, watchers) -> Thread | None:
    try:
        devicesWatcher = DevicesWatcher(config, 
                        lambda rules: activate_rules(rules, watchers), 
                        lambda rules: deactivate_rules(rules, watchers))
        
        devWatcher = threading.Thread(target=devicesWatcher.run, name="device-watcher")
        devWatcher.daemon = True
        devWatcher.start()
        return devWatcher
        
    except Exception as ex:
        notify_message(str(ex), DEVICE_MONITORING_CAT)
        return None


def main():
    print(TITLE)

    try:
        global log_file
        log_file = open("events.log", "w")
        path = os.path.realpath(__file__)
        notify_message('Started from: ' + path)

        try_add_to_registry(path, APPLICATION_NAME)
        current_folder, _ = os.path.split(__file__)
        config = try_read_config(current_folder)
        config.accept(ConfigurationValidationVisitor())
        active_drives_visitor = ConfigurationUpdateActiveDrivesVisitor()
        config.accept(active_drives_visitor)
        watchers = []
        ensure_data_is_backuped(config.includes, watchers)
        
        notify_message("Running Monitor...")
        observe_file_system(watchers)

        run_device_watcher(config, watchers)

        try:
            while True:
                input()
        except KeyboardInterrupt:
            print(APPLICATION_NAME + " monitoring is interrupted")

    except Exception as any_error:
        notify_message(any_error)
        input()

def on_exit_handler():
    print('<exited>')
    log_file.close()

if __name__ == "__main__":
    atexit.register(on_exit_handler)
    main()

