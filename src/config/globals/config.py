import sys
import os
# Add the project root to sys.path for direct script execution


from datetime import datetime, time
from src.config.globals.email_manager import EMAIL_MANAGER
from src.config.globals.addresses import ADDR
from src.config.globals.log_setup import LOG, customSMTPHandler
from src.config.globals.signals import SIGNALS
import logging
from src.markets.markets import US_MARKET
import numpy as np
from src.account.account import Account
from src.trades.strategy.strategy import Strategy
import os
import pandas as pd
import pickle
import re
from threading import Lock
import time as sleeper


class OMS_Settings:
    # originally config settings were located in an Excel file, and loaded via the load_config function in Config class
    # however, as the gui was developed some settings were migrated into a serialised file.  The serialised file
    # contains an OMS_Settings object.  As more settings are migrated from the Excel config file they can be added here.

    def __init__(self):
        self.process_orders_basis: str = 'SCHEDULED'  # either 'MANUAL' or 'SCHEDULED'
        self.scheduled_order_processing_time: time = time(22, 0)

    def update_serialised_settings(self, values_dict):
        for k, v in values_dict.items():
            setattr(self, k, v)
        self.save_serialised_settings()

    def validate(self):
        if self.process_orders_basis not in ['MANUAL', 'SCHEDULED']:
            raise ValueError('Orders processing basis must be either MANUAL or SCHEDULED')

    @property
    def file_path(self):
        return os.path.join(ADDR.folder_oms_data, 'OMS Settings')

    def save_serialised_settings(self):
        self.validate()
        with open(self.file_path, 'wb') as f:
            pickle.dump(self, f)

    def load_serialised_settings(self):
        if os.path.isfile(self.file_path):
            try:
                with open(self.file_path, 'rb') as f:
                    settings = pickle.load(f)
                for k, v in vars(settings).items():
                    setattr(self, k, v)
            except EOFError:
                pass
        else:
            self.save_serialised_settings()


class Config:
    # This loads and retains all data from the Excel config file.

    def __init__(self):

        self.config = dict()
        self._config = dict()  # used for loading new settings; enables continuous availability of self.config
        self._config_lock = Lock()
        self._config_file_last_modified = None
        self._config_file_last_loaded = datetime.now()

        self.trading_accounts = []
        self.strategies = []
        self.ignored_positions = []

    def load_config(self):

        # The 'QAOMS Config.xlsx' file contains all the settings for accounts, trading systems and other parameters
        # that control trading activities.  The file should be saved in the \...\Quant Alpha OMS Data\Config File\
        # folder. The config file is reloaded each time a new order file is attached, to allow for adjustments to
        # trade settings, so the config file can be edited live (remember to save changes) while the OMS is running.

        # load_config is called from multiple locations so a lock is employed to prevent simultaneous access
        self._config_lock.acquire(blocking=True)

        config_file_path = f'{ADDR.folder_config}\\QAOMS Config.xlsx'
        required_settings = ['Email Sending Address', 'Email Username', 'Email Password', 'Email Host Address',
                             'SMTP Port', 'Email Recipients', 'RT Output File Time',
                             'Daily Report Time', 'Ignore IB Errors', 'Report on Advisor Account',
                             'Max Short Margin', 'Max Fee Rate', 'DarkIce']

        # check that the file exists; if not, prompt user once, then keep checking until it is available.
        error_thrown = False
        while not os.path.isfile(config_file_path):
            if not error_thrown:
                SIGNALS.raise_oms_error.emit((2,
                                              FileNotFoundError(f"Please save the config file as 'QAOMS Config.xlsx' "
                                                                f"into the folder {ADDR.folder_config}."),
                                              True))
                error_thrown = True
            sleeper.sleep(2)

        # check if the config file has any saved changes
        if self._config_file_last_modified and \
                self._config_file_last_modified == os.path.getmtime(config_file_path) and \
                self._config_file_last_loaded.date() == datetime.now().date():
            # config file has no saved changes since the last time it was loaded
            self._config_lock.release()
            return
        else:
            # the config file has modifications - load them.
            self._config_file_last_modified = os.path.getmtime(config_file_path)
            self._config_file_last_loaded = datetime.now()

        # reload accounts, strategies and ignored_positions each time config is loaded.
        self.trading_accounts, self.strategies, self._config, self.ignored_positions = [], [], dict(), []

        LOG.debug(f'Loading configuration from {ADDR.folder_config}\\QAOMS Config.xlsx')

        valid_config_file = False
        while not valid_config_file:

            # get config settings, including email address recipients for error notifications
            with pd.ExcelFile(f'{ADDR.folder_config}\\QAOMS Config.xlsx') as xls:
                settings = pd.read_excel(xls, 'Settings', index_col=0, header=0).to_records()
                for s in settings:
                    self._config[s[0]] = s[1]
                missing_settings = [s for s in required_settings if s not in self._config.keys()]
                if missing_settings:
                    raise ValueError(f'The config.xlsx file is missing these settings: '
                                     f'{", ".join(missing_settings)}. Update the file with the '
                                     f'required settings and restart the OMS.')

                if isinstance(self._config['Ignore IB Errors'], int):
                    self._config['Ignore IB Errors'] = str(self._config['Ignore IB Errors'])
                self._config['Ignore IB Errors'] = [int(e) for e in (self._config['Ignore IB Errors']).split(',')]

                email_list = (self._config['Email Recipients']).split(',')
                regex = "^.+\\@(\\[?)[a-zA-Z0-9\\-\\.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(\\]?)$"
                if '@' in self._config['Email Host Address']:
                    raise ValueError('Invalid SMTP Host address provided.  Do not enter email '
                                     'addresses in the Email Host Address field. Host addresses '
                                     'look something like: "smtp.mail.yahoo.com"')
                for email in email_list:
                    if not (len(email) > 7 and re.fullmatch(regex, email)):
                        raise ValueError(f"Invalid Email provided in settings file: {email}")
                self._config['ToAddrs'] = email_list

            # DEPRECATED.  Email management now in separate class
            # for smtp_handler in [h for h in LOG.handlers if type(h) == customSMTPHandler]:
            #     smtp_handler.fromaddr = self._config['Email Sending Address']
            #     smtp_handler.mailhost = self._config['Email Host Address']
            #     smtp_handler.mailport = self._config['SMTP Port']
            #     smtp_handler.password = self._config['Email Password']
            #     smtp_handler.toadds = email_list
            #     smtp_handler.username = self._config['Email Username']

            EMAIL_MANAGER.smtp_server = self._config['Email Host Address']
            EMAIL_MANAGER.smtp_port = self._config['SMTP Port']
            EMAIL_MANAGER.smtp_user = self._config['Email Username']
            EMAIL_MANAGER.smtp_password = self._config['Email Password']
            EMAIL_MANAGER.from_email = self._config['Email Sending Address']
            EMAIL_MANAGER.to_emails = email_list
            for smtp_handler in [h for h in LOG.handlers if type(h) == customSMTPHandler]:
                smtp_handler.email_notifier = EMAIL_MANAGER

            # assign recipient email addresses to all email loggers
            for log in logging.root.manager.loggerDict:
                if 'handlers' in vars(logging.root.manager.loggerDict[log]):
                    for h in logging.root.manager.loggerDict[log].handlers:
                        if 'toaddrs' in vars(h):
                            vars(h)['toaddrs'] = self._config['ToAddrs']

            # get ignored positions
            with pd.ExcelFile(f'{ADDR.folder_config}\\QAOMS Config.xlsx') as xls:
                df = pd.read_excel(xls, 'Ignored Positions', header=0, index_col=0)
                df['Ignored Position'] = df[['Contract ID', 'Ignored Position Size']].values.tolist()
                ignored_positions = df.groupby('Account ID', group_keys=True)['Ignored Position'].apply(
                    list).to_dict()
                ignored_positions = {key.upper(): [[int(ip[0]), ip[1]] for ip in val] for
                                     key, val in ignored_positions.items()}

            # get account list and strategy list
            with pd.ExcelFile(f'{ADDR.folder_config}\\QAOMS Config.xlsx') as xls:
                accounts = pd.read_excel(xls, 'Accounts', index_col=0, header=0, na_filter=False)
                strategies = pd.read_excel(xls, 'Strategies', index_col=0, header=0)

            # STRATEGIES CONFIG
            df = strategies
            strategy_ids = list(df.iloc[0].index)

            if not strategy_ids[0] == 'ID':
                raise ValueError("Incorrectly formatted Strategies sheet in config file.  First row must have headings "
                                 "'Account', 'ID', followed by strategy ID's.")
            if len(list(set(strategy_ids))) != len(strategy_ids):
                raise ValueError("Duplicate strategy ids found in Strategies sheet in config file. Strategy ids must "
                                 "be unique.")
            invalid_directions = [x.upper() for x in df.iloc[0] if x.upper() not in ['LONG', 'SHORT', 'DIRECTION']]
            if invalid_directions:
                raise ValueError(f"Invalid direction ({invalid_directions[0]}) specified on Strategies sheet in config "
                                 f"file.  Directions must be either 'LONG' or 'SHORT'")
            for account in accounts.columns:
                if len([a for a in list(df.index) if a == account]) != 2:
                    raise ValueError(f'Invalid Strategies specification in Config file for account {account}.  '
                                     f'All accounts must have exactly two rows on the Strategies file, designating '
                                     f'PrimarySecurity and SecondarySecurity.')
            invalid_account_ids = [a for a in df.index[1:] if a not in accounts.columns]
            if invalid_account_ids:
                raise ValueError(f"Invalid account ids found in Column 1 of Strategies sheet in Config file: "
                                 f"{invalid_account_ids}")

            strategy_ids = [s for s in strategy_ids[1:] if s not in [None, '', np.nan]]
            for strategy_id in strategy_ids:
                # Model ID is not recorded in the config file.  Model ID, obtained from an RawOrder ModelID ref, is
                # added to a copy of the strategy object and saved to the trade record just before the trade is placed.
                strategy = Strategy(qa_id=strategy_id.upper(),
                                    qa_model='',
                                    direction=df.iloc[0][strategy_id].upper())
                if strategy.valid():
                    self.strategies.append(strategy)

            # get security types per account, per strategy
            account_security_types = {}
            # keys = account_id, values = {strategy id: [primary sec type, secondary sec type]}
            for account_id, row in df.iloc[1:].iterrows():
                if account_id not in account_security_types.keys():
                    account_security_types[account_id] = {strategy_id.upper(): [None, None]
                                                          for strategy_id in strategy_ids}
                if row.iloc[0] not in ['PrimarySecurity', 'SecondarySecurity']:
                    raise ValueError(
                        f"Column 2 of the Strategies sheet in the Config file must specify 'PrimarySecurity' or "
                        f"'SecondarySecurity'.  Invalid value found: {row[0]}")
                for strategy_id in strategy_ids:
                    sec_type = row[strategy_id]
                    if isinstance(sec_type, float) and np.isnan(sec_type):
                        sec_type = ''
                    if row.iloc[0] == 'PrimarySecurity':
                        account_security_types[account_id][strategy_id.upper()][0] = sec_type
                    else:
                        account_security_types[account_id][strategy_id.upper()][1] = sec_type

            # ACCOUNTS CONFIG
            for account_id in [a for a in accounts.columns if 'Unnamed' not in a]:
                df = accounts[account_id]
                allocations = df.iloc[df.index.get_loc('Strategy Allocations') + 1:].copy().replace('', 0)
                account_id = account_id.upper()
                allocations.index = allocations.index.str.upper()

                # validate that all strategies listed in the account are also in the strategies page, and vice versa
                for strategy_id in allocations.index:
                    if strategy_id.upper() not in [s.qa_id for s in self.strategies]:
                        raise ValueError(f'Allocation to unknown strategy {strategy_id} in Account '
                                         f'{account_id} in config file.')
                if [s for s in self.strategies if s.qa_id not in [i.upper() for i in allocations.index]]:
                    raise ValueError(f'Account {account_id} has incomplete strategy allocations in config file.')

                account = Account(id=account_id,
                                  alias=df['Alias'].upper(),
                                  ib_type=df['Account Type'].upper(),
                                  ib_algo=df['IB Algo'].upper(),
                                  ib_platform=df['IB Platform'].upper(),
                                  ib_port=df['IB Port'],
                                  ib_client_id=df['IB Client #'],
                                  strategy_allocations=allocations.to_dict(),
                                  strategy_security_types=account_security_types[account_id],
                                  ignored_positions=[],
                                  parent_account=df['Parent Account'].upper())
                if account_id in ignored_positions.keys():
                    account.ignored_positions = ignored_positions[account_id]
                try:
                    account.valid()

                    # set up daily log for account, if not already
                    if not os.path.isdir(f'{ADDR.folder_log_files}\\{account.alias}'):
                        os.mkdir(f'{ADDR.folder_log_files}\\{account.alias}\\')
                    log_name = f'{account.alias} Log {datetime.strftime(US_MARKET.current_time.date(), "%Y%m%d")}.txt'
                    if not account.log:
                        account_log = logging.getLogger(log_name)
                        account_log.setLevel(logging.DEBUG)
                        # can't use TimedRotatingFileHandler because it is timezone naive
                        file_handler = logging.FileHandler(f'{ADDR.folder_log_files}\\{account.alias}\\{log_name}',
                                                           mode='a')
                        file_handler.setLevel(logging.INFO)
                        file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s - %(message)s'))
                        account_log.addHandler(file_handler)
                        global_handlers = [h for h in LOG.handlers if h.name in ['Global Debug Log',
                                                                                 'Stream Handler Out',
                                                                                 'Steam Handler Err',
                                                                                 'SMTP Handler',
                                                                                 'Stream Handler', 'GUI Handler']]
                        for h in global_handlers:
                            account_log.addHandler(h)
                        account.log = account_log

                    self.trading_accounts.append(account)

                except (ValueError, NotADirectoryError) as error:
                    raise error

            # Client ID's must be unique
            primary_accounts = [a for a in self.trading_accounts if a.ib_type != 'MANAGED']
            if len(primary_accounts) != len(list(set([(a.ib_port, a.ib_client_id) for a in primary_accounts]))):
                # client ids for each account must be unique for each TWS instance.  No duplication is allowed.
                raise ValueError("Duplicate Port/Client IDs found in Config File. "
                                 "Each account must have a unique Port and IB Client # combination")

            # Account ID's must be unique
            if len(list(set([account.id for account in self.trading_accounts]))) != len(self.trading_accounts):
                raise ValueError('Duplicate account ids found in config file. Each account must '
                                 'have a unique IB Account ID.')
            # Account Aliases must be unique
            if len(list(set([account.alias for account in self.trading_accounts]))) != len(self.trading_accounts):
                raise ValueError('Duplicate Customer IDs found in config file. Each account must '
                                 'have a unique Customer ID (alias).')

            # Strategy ID's must be unique
            if len(list(set([strategy.qa_id for strategy in self.strategies]))) != len(self.strategies):
                raise ValueError('Duplicate strategy ids found in config file.')

            # DEPOSITS AND WITHDRAWALS
            self._config['Funds'] = []
            with pd.ExcelFile(f'{ADDR.folder_config}\\QAOMS Config.xlsx') as xls:
                try:
                    df = pd.read_excel(xls, 'Funds', header=0, index_col=0).fillna(0)
                    for account, row in df.iterrows():
                        # fund changes are stored as a list of [account id, change date, change amount]
                        try:
                            item = [account, row.iloc[0].date(),  row.iloc[1] + row.iloc[2]]
                        except AttributeError:
                            # if dates are entered in incorrect format an error will be raised
                            raise ValueError(f'Incorrect format for date in Config Deposit/Withdrawals tab:'
                                             f' {row.iloc[0]}')
                        self._config['Funds'].append(item)
                except ValueError:
                    raise ValueError('Config file must have sheet named "Funds", with columns '
                                     'Account, Date, Deposit, Withdrawal.')

            self.config = self._config.copy()  # ensures continuous availability of self.config
            valid_config_file = True
            self._config_lock.release()
            SIGNALS.config_update.emit()


OMS_CONFIG = Config()           # most settings still here, as recorded in excel config file
OMS_SETTINGS = OMS_Settings()   # some settings now here, as set/recorded in gui.  Eventually migrate all settings here.

if __name__ == "__main__":
    # Get the directory containing this file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate up to the project root (Algo_Terminal directory)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    config = Config()
    config.load_config()
    print(config.trading_accounts)

