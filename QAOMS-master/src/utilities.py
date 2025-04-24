from datetime import datetime, timedelta
import fnmatch
import logging
import logging.handlers
import os
import shutil
import sys
from types import ModuleType, FunctionType
from gc import get_referents

class CodeTimer:

    def __init__(self):
        self.timer_start = datetime.now()
        self.timer_end = None
        self.laps = dict()

    def start(self):
        self.timer_start = datetime.now()

    def lap(self, lap_name: str):
        if lap_name not in self.laps.keys():
            self.laps[lap_name] = {}
            self.laps[lap_name]['Count'] = 0
            self.laps[lap_name]['Total'] = 0
            self.laps[lap_name]['Minimum'] = 0
            self.laps[lap_name]['Maximum'] = 0
            self.laps[lap_name]['Avg'] = 0

        lap = self.end()
        self.laps[lap_name]['Count'] += 1
        if lap < self.laps[lap_name]['Minimum'] or self.laps[lap_name]['Minimum'] == 0:
            self.laps[lap_name]['Minimum'] = lap
        if lap > self.laps[lap_name]['Maximum']:
            self.laps[lap_name]['Maximum'] = lap
        self.laps[lap_name]['Total'] += lap
        self.laps[lap_name]['Avg'] = self.laps[lap_name]['Total']/self.laps[lap_name]['Count']

        return f"{lap_name} [{round(self.laps[lap_name]['Minimum'],3)} - {round(self.laps[lap_name]['Avg'],3)} " \
               f"- {round(self.laps[lap_name]['Maximum'],3)}]"

    def end(self):
        self.timer_end = datetime.now()
        duration = (self.timer_end - self.timer_start).total_seconds()
        return duration


class dot_dict(dict):

    # subclass of a dict that allows keys to be accessed using dot notation

    def __getattr__(self, attr):
        if attr in self:
            return self[attr]
        else:
            raise AttributeError(f'{attr} not found')

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


class SingleLevelFilter(logging.Filter):

    def \
            __init__(self, passlevel, reject):
        super().__init__()
        self.passlevel = passlevel
        self.reject = reject

    def filter(self, record):
        if self.reject:
            return record.levelno != self.passlevel
        else:
            return record.levelno == self.passlevel


class ColoredFormatter(logging.Formatter):
    """
    Color	Foreground Code	Background Code
    Black	\033[30m	\033[40m
    Red	    \033[31m	\033[41m
    Green	\033[32m	\033[42m
    Yellow	\033[33m	\033[43m
    Blue	\033[34m	\033[44m
    Magenta	\033[35m	\033[45m
    Cyan	\033[36m	\033[46m
    White	\033[37m	\033[47m
    """

    def format(self, record):
        # Add ANSI escape codes to color the log level
        if record.levelno == logging.DEBUG:
            prefix = '\033[0;30mDEBUG:\033[0;30m '
        elif record.levelno == logging.INFO:
            prefix = '\033[0;30mINFO: \033[0;30m '
        elif record.levelno == logging.WARNING:
            prefix = '\033[0;31mALERT:\033[0;31m '
        elif record.levelno == logging.ERROR:
            prefix = '\033[0;31mERROR:\033[0;31m '
        elif record.levelno == logging.CRITICAL:
            prefix = '\033[1;31mCRITICAL:\033[1;31m '
        else:
            prefix = ''
        # Call the parent class's format method to get the log message
        message = super().format(record)
        # Combine the prefix and message and return the result
        return prefix + message


def case(value, compare_values, return_values, fail_value):
    # like excel SWITCH function
    # compare_values and return_values are lists of identical length
    new_value = fail_value
    if len(compare_values) == len(return_values):
        try:
            new_value = return_values[compare_values.index(value)]
        except ValueError:
            new_value = fail_value
    return new_value


def timer_display_text(seconds_remaining, display='sec'):
    days = seconds_remaining // 86400
    hours = (seconds_remaining % 86400) // 3600
    mins = (seconds_remaining % 3600) // 60
    secs = seconds_remaining % 60
    timer_text = ''
    if display.lower() == 'min':
        if hours > 0:
            timer_text = '{:0>2.0f}:{:0>2.0f} hh:mm'.format(hours, mins)
        else:
            timer_text = '{:0>2.0f} min'.format(mins)
    elif display.lower() == 'sec':
        if days > 0:
            timer_text = '{} d {:0>2.0f} h {:0>2.0f} m'.format(int(days), hours, mins)

        elif hours > 0:
            timer_text = '{:0>2.0f}:{:0>2.0f}:{:0>2.0f}'.format(hours, mins, secs)
        else:
            timer_text = '{:0>2.0f}:{:0>2.0f}'.format(mins, secs)
    return timer_text


def backup_project(destination_folder=None):
    if not destination_folder:
        destination_folder = 'X:\\1. Trading\\7. Algorithmic Trading\\Code Library\\Backups from Code on Local Drive'
    project_directory = os.getcwd()
    timestamp = datetime.strftime(datetime.now() - (datetime.now() - datetime.min) % timedelta(minutes=15),
                                  '%Y%m%d %H%M')
    project_name = project_directory.rsplit('\\', 1)[1]
    backup_folder_name = project_name + ' ' + timestamp
    backup_path = os.path.join(destination_folder, backup_folder_name)

    if not os.path.isdir(backup_path):
        for root, dirs, files in os.walk(project_directory):
            for filename in files:
                if fnmatch.fnmatch(filename, '*.py'):
                    source_path = os.path.join(root, filename)
                    dest_path = os.path.join(backup_path, filename)
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(source_path, backup_path)

    for f in os.listdir(destination_folder):
        if project_name in f and os.path.isdir(os.path.join(destination_folder, f)) and f != backup_folder_name:
            shutil.rmtree(os.path.join(destination_folder, f))


class file_utilities:

    @staticmethod
    def file_is_open(file_path):
        # note this is windows specific; other operating systems will allow renaming of a file that is open.

        if not os.path.exists(file_path):
            return True

        try:
            file_name = os.path.basename(file_path)
            extension = '.' + file_name.split('.')[1]
            temp_file_name = file_path.replace(file_name, f'Temp{extension}')
            os.rename(file_path, temp_file_name)
            os.rename(temp_file_name, file_path)
            return False
        except (OSError, PermissionError):
            return True

