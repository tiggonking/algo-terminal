import os
from tkinter.filedialog import askdirectory


class AddressGlobals:
    def __init__(self):

        self.ini_file_path = os.path.join(os.getenv('LOCALAPPDATA'), 'QA OMS', 'ini.txt')

        if os.path.isfile(self.ini_file_path):
            with open(self.ini_file_path, 'r') as f:
                master_folder = f.read()
        else:
            master_folder = ''
            os.makedirs(os.path.dirname(self.ini_file_path), exist_ok=True)

        while not os.path.isdir(master_folder):
            master_folder = askdirectory(title='SELECT THE MASTER (PARENT) FOLDER TO STORE OMS DATA:').replace('/',
                                                                                                            '\\')
            with open(self.ini_file_path, 'w') as f:
                f.write(master_folder)

        self.master_folder = master_folder

        # Orders Folder
        self.folder_order_files = self.create_if_not_exists(f'{self.master_folder}\\Order Files\\')
        self.create_if_not_exists(f'{self.folder_order_files}\\Processed\\')
        self.create_if_not_exists(f'{self.folder_order_files}\\Order File Template\\')

        # Trade History Folder
        self.folder_output_trade_lists = self.create_if_not_exists(f'{self.master_folder}\\Trade History\\')
        self.folder_output_trade_exports = self.create_if_not_exists(
            f'{self.folder_output_trade_lists}\\Trade Exports\\')
        self.create_if_not_exists(f'{self.folder_output_trade_lists}\\Archive\\')

        # Daily Reports Folder
        self.folder_daily_reports = self.create_if_not_exists(f'{self.master_folder}\\Daily Reports\\')

        # OMS Files Folders - config, trade registers and log files
        self.folder_oms_data = self.create_if_not_exists(f'{self.master_folder}\\OMS System Files\\')
        self.folder_config = self.create_if_not_exists(os.path.join(self.folder_oms_data, 'Configuration'))
        self.folder_trade_registers = self.create_if_not_exists(f'{self.folder_oms_data}\\Trade Registers')
        self.folder_trade_register_backups = self.create_if_not_exists(f'{self.folder_trade_registers}\\BACKUPS')
        self.folder_log_files = self.create_if_not_exists(f'{self.folder_oms_data}\\Logs')
        self.folder_stack_traces = self.create_if_not_exists(f'{self.folder_oms_data}\\Stack Traces')

        # Performance Folder
        self.folder_performance = self.create_if_not_exists(f'{self.master_folder}\\Performance\\')

        for f_name in vars(self):
            if f_name != 'ini_file_path':
                self.create_if_not_exists(vars(self)[f_name])

    @staticmethod
    def create_if_not_exists(folder_address):
        if not os.path.isdir(folder_address):
            os.mkdir(folder_address)
        return folder_address


ADDR = AddressGlobals()
