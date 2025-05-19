from globals.addresses import ADDR
from globals.log_setup import LOG
from globals.signals import SIGNALS
from src.trades.orders.raw_orders import RawOrder
import os
import numpy as np
import pandas as pd
from pathlib import Path
import shutil
import time as sleeper
import traceback
import utilities as util

file_util = util.file_utilities()


class FileWatcher:

    def __init__(self):
        self.order_data = []  # a list of tuples of (file_name, [list of orders])
        self.testing_mode = False
        self.required_columns = ['Symbol', 'Date', 'Exchange', 'MaxExp', 'MaxNewExp', 'Action', 'IsExit', 'PctPosSize',
                                 'OrderRank', 'Currency', 'Order Type', 'Lmt Price', 'Time In Force', 'ModelID',
                                 'AccountID', 'SpecialOrder', 'GoodTilTime', 'PriceCondition', 'IBAlgo', 'PriorClose']

    def check_for_order_files(self):
        if self.testing_mode:
            sleeper.sleep(3)
            shutil.copy(os.path.join(ADDR.folder_order_files, 'Processed', 'LMRA_Orders.csv'),
                        os.path.join(ADDR.folder_order_files, 'Orders.csv'))
        files = os.listdir(ADDR.folder_order_files)
        for f in files:
            file_path = os.path.join(ADDR.folder_order_files, f)
            if os.path.isfile(file_path):
                if file_util.file_is_open(file_path):
                    LOG.warning(f'Please save and close the order file {file_path}')
                while file_util.file_is_open(file_path):
                    sleeper.sleep(1)
                order_data = None
                LOG.debug(f'Evaluating file "{f}" in order file folder')
                try:
                    order_data = self.validate_and_load_order_file(file_path)
                except (ValueError, ImportError, FileNotFoundError) as e:
                    LOG.error(f'INVALID ORDER FILE ({Path(file_path).name}): {e}')
                except TypeError as e:
                    if e.args[0] == 'Parser must be a string or character stream, not int':
                        LOG.error(f'INVALID DATA FORMAT in order file ({Path(file_path).name}). Please ensure '
                                  f'dates are formatted dd/mm/yyyy and try again.')
                    else:
                        LOG.error(f'INVALID ORDER FILE ({Path(file_path).name}): {e}')

                if order_data == 'empty file':
                    # empty files are acceptable, not invalid
                    self.move_file(f, file_path)
                elif order_data:
                    self.move_file(f, file_path)
                    self.order_data.append((f, order_data))
                    LOG.info("#" * shutil.get_terminal_size()[0])
                    LOG.info(f'{len(order_data)} orders loaded from file {f}')
                    LOG.info("#" * shutil.get_terminal_size()[0])
                else:
                    # file is invalid in some way
                    LOG.info(f'\r\nTo initiate trading, please correct errors in order file and save'
                             f' it again to {ADDR.folder_order_files}\n')
                    shutil.move(file_path, os.path.join(ADDR.folder_order_files, 'Processed',
                                                        f'INVALID - {Path(file_path).name}'))

    def move_file(self, file_name, file_path):
        success, error_logged = False, False
        while not success:
            try:
                shutil.move(file_path, os.path.join(ADDR.folder_order_files, 'Processed', file_name))
                success = True
            except PermissionError:
                if not error_logged:
                    self.raise_error(2, PermissionError(f'Cannot move the orders file {file_path} - '
                                                        f'is it open?'), False)
                error_logged = True
                sleeper.sleep(2)

    def validate_and_load_order_file(self, file_path):
        csv_orders = []
        file_type = file_path.rsplit('.', 1)[1]
        if not os.path.isfile(file_path):
            self.raise_error(3, FileNotFoundError(f'Error reading {file_path}.  Please copy the file there again.'))
        if file_type.upper() == 'CSV':
            df = self.load_file(file_path)
            if df is not None:
                if 'Symbol' in df.keys():
                    df.dropna(subset=['Symbol'], inplace=True)
                if df is not None and not df.empty:
                    if set(self.required_columns).issubset(df.columns):
                        for idx, row in df.iterrows():
                            csv_order = RawOrder(ticker=row['Symbol'].upper(), date_str=row['Date'],
                                                 exchange=row['Exchange'].upper(), max_exposure=row['MaxExp'],
                                                 max_new_exposure=row['MaxNewExp'],
                                                 action=row['Action'].upper(), is_exit=row['IsExit'],
                                                 pos_size_pct=row['PctPosSize'], order_rank=row['OrderRank'],
                                                 currency=row['Currency'], order_type=row['Order Type'],
                                                 order_price=row['Lmt Price'], tif=row['Time In Force'],
                                                 strategy_model_string=row['ModelID'].upper(),
                                                 account_id=row['AccountID'],
                                                 order_type_special=row['SpecialOrder'],
                                                 gtd_time=row['GoodTilTime'],
                                                 price_condition=row['PriceCondition'],
                                                 ib_algo=row['IBAlgo'],
                                                 prior_close=row['PriorClose'])
                            csv_orders.append(csv_order)
                        if csv_orders:
                            # validate set of orders
                            for strategy in list(set([order.qa_strategy_id for order in csv_orders])):
                                strategy_orders = [o for o in csv_orders if o.qa_strategy_id == strategy]
                                if len(list(set([ordr.max_exposure for ordr in strategy_orders]))) > 1 or \
                                        [ordr for ordr in strategy_orders if np.isnan(ordr.max_exposure)]:
                                    self.raise_error(2, ValueError(f'{os.path.basename(file_path)} - Conflicting or '
                                                                   f'missing max positions settings for strategy '
                                                                   f'{strategy}'), True)
                                    return None
                                elif len(list(set([ordr.max_new_exposure for ordr in strategy_orders]))) > 1 or \
                                        [ordr for ordr in strategy_orders if np.isnan(ordr.max_new_exposure)]:
                                    self.raise_error(2, ValueError(f'{os.path.basename(file_path)} - Conflicting or '
                                                                   f'missing max daily entries settings '
                                                                   f'for strategy {strategy}'), True)
                                    return None
                            return csv_orders
                        else:
                            return None
                    else:
                        self.raise_error(3, ValueError(f'{os.path.basename(file_path)} - Missing column(s): '
                                         f'{", ".join([c for c in self.required_columns if c not in df.columns])}'))
                else:
                    LOG.debug(f'ORDER FILE {os.path.basename(file_path)} - File contains no orders')
                    return 'empty file'
            else:
                self.raise_error(3, ImportError(f'{os.path.basename(file_path)} - could not load order file'))

        else:
            self.raise_error(3, TypeError(f'{os.path.basename(file_path)} - only CSV files can be processed'))

    @staticmethod
    def load_file(path):
        n, finish, df = 0, False, None
        while not finish:
            try:
                df = pd.read_csv(path)
                finish = True
            except (FileNotFoundError, PermissionError):
                n += 1
                if n < 5:
                    sleeper.sleep(n)
                else:
                    finish = True

        return df

    def raise_error(self, level, exception, stop_signal=False):
        # this handles EXCEPTIONS (only) which result in the OMS or the orders being stopped.
        # Other errors (e.g. an invalid order in the imported orders) are logged directly.
        trace = traceback.format_exception(exception)
        try:
            error_text = exception.args[0]
        except IndexError:
            error_text = traceback.format_exception_only(exception)
        SIGNALS.exception.emit((level, error_text, stop_signal, trace))


if __name__ == '__main__':
    file_handler = FileWatcher()
    while True:
        input('Ready')