#!/usr/bin/env python


#############################################################################
#
# Copyright (C) 2013 Riverbank Computing Limited.
# Copyright (C) 2010 Nokia Corporation and/or its subsidiary(-ies).
# All rights reserved.
#
# This file uses PyQt6, which is under the following licence.
#
# $QT_BEGIN_LICENSE:BSD$
# You may use this file under the terms of the BSD license as follows:
#
# "Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in
#     the documentation and/or other materials provided with the
#     distribution.
#   * Neither the name of Nokia Corporation and its Subsidiary(-ies) nor
#     the names of its contributors may be used to endorse or promote
#     products derived from this software without specific prior written
#     permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE."
# $QT_END_LICENSE$
#
#############################################################################

from decimal import Decimal
import threading
from datetime import datetime, timedelta
from globals.addresses import ADDR
from globals.email_manager import EMAIL_MANAGER
from globals.log_setup import customSMTPHandler
from globals.config import OMS_SETTINGS
from globals.signals import SIGNALS
import logging
from markets import US_MARKET
import os
from PyQt6.QtCore import (pyqtSignal, pyqtSlot, QBasicTimer, QDateTime, QObject, QRunnable, Qt, QThreadPool,
                          QTime, QTimer, QUrl)
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QMainWindow, QCheckBox, QComboBox, QTimeEdit, QDateEdit,
                             QDateTimeEdit, QDial, QDialog, QFormLayout, QGridLayout, QGroupBox, QHeaderView,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QRadioButton,
                             QScrollBar, QSizePolicy, QSlider, QSpinBox, QStyleFactory, QTableWidget, QTableWidgetItem,
                             QTabWidget, QTextEdit, QVBoxLayout, QWidget, QInputDialog)
from PyQt6.QtGui import QColor, QBrush, QFont, QFontMetrics, QDesktopServices
import time
import utilities
import sys
import traceback

global_green = "#00B050"      # QColor(0, 176, 80)
global_red = "#FF9999"        # QColor(255, 153, 153)
global_blue = "#203764"       # QColor(32, 55, 100)
global_orange = "#FFBC37"     # QColor(255, 188, 55)
global_grey_text = "#ACB9CA"  # QColor(172, 185, 202)


class QTableLogger(logging.Handler):
    # custom handler to enable stream logging to the gui
    def __init__(self):
        super(QTableLogger, self).__init__()

        self.record_queue = []

    def emit(self, record):
        SIGNALS.log_record.emit(record)

    def write(self):
        pass


class NoScrollComboBox(QComboBox):
    def wheelEvent(self, event):
        event.ignore()


class OMSgui(QMainWindow):

    def __init__(self, oms_instance):
        super().__init__()

        # threads & locks
        self.gui_lock = threading.Lock()

        # gui signals
        SIGNALS.config_update.connect(self.slot_write_config_to_gui)
        SIGNALS.start_timers.connect(self.slot_start_timers)
        SIGNALS.trade_data_updated.connect(self.slot_update_trade_table)
        SIGNALS.log_record.connect(self.slot_update_log)
        SIGNALS.exception.connect(self.slot_exception_handling)
        SIGNALS.raw_order_update.connect(self.slot_raw_order_update)
        SIGNALS.trade_history_generated.connect(self.slot_trade_history_updated)

        # create log table
        self.log_table = QTableWidget(self)
        self.log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.setColumnCount(3)
        self.log_table.setColumnWidth(0, 140)
        self.log_table.setColumnWidth(1, 80)
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.setHorizontalHeaderLabels(['Time', 'Level', 'Message'])
        self.log_table.horizontalHeader()

        # set up logger
        self.logger = logging.getLogger('OMS')
        self.logger.setLevel(logging.DEBUG)
        handler = QTableLogger()
        handler.setLevel(logging.INFO)
        handler.table_lock = self.gui_lock
        handler.name = 'GUI Handler'
        self.logger.addHandler(handler)
        self.log_table_queue = []

        self.oms = oms_instance
        self.daily_report_timer = QTimer(self)
        # noinspection PyUnresolvedReferences
        self.daily_report_timer.timeout.connect(self.daily_report)
        self.rt_output_timer = QTimer(self)
        # noinspection PyUnresolvedReferences
        self.rt_output_timer.timeout.connect(self.rt_output_file)

        for a in self.oms.trading_accounts:
            a.log.addHandler(handler)

        # set up tab variables
        self.header_widget = QWidget()
        self.tab_widget = QTabWidget()
        self.oms_tab = utilities.dot_dict()
        self.config_tab = utilities.dot_dict()
        self.trades_tab = utilities.dot_dict()
        self.orders_tab = utilities.dot_dict()
        self.tab_positions = utilities.dot_dict()

        # create header bar
        self.header_oms_status = QLabel('OMS Stopped - Check Log for Details and Restart')
        self.header_oms_status.setFont(QFont(QApplication.font().family(), 16))
        self.header_oms_status.font().setBold(True)
        self.header_oms_status.setStyleSheet('color: red')

        # create tabs
        central_widget = QWidget()
        self.left_bar_width = 250
        self.create_oms_tab()
        self.create_trades_tab()
        self.create_orders_tab()
        self.create_config_tab()
        self.update_accounts_list()

        # create layout
        tabsLayout = QHBoxLayout()
        tabsLayout.addWidget(self.tab_widget)
        # tabsLayout.addStretch(1)
        top_layout = QVBoxLayout()
        top_layout.addWidget(self.header_oms_status)
        top_layout.addLayout(tabsLayout)
        central_widget.setLayout(top_layout)
        self.setLayout(top_layout)
        self.header_oms_status.hide()

        # set main window settings
        self.adjustSize()
        self.setCentralWidget(central_widget)
        self.setWindowTitle("Quantive Alpha OMS")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.resize(1600, 600)
        self.showMaximized()

        # start oms in a thread
        oms_thread = threading.Thread(target=self.oms.run, name='OMS Thread')
        oms_thread.start()
        self.update_accounts_list()

        # update gui at 1 second intervals
        timer = QTimer(self)
        # noinspection PyUnresolvedReferences
        timer.timeout.connect(self.update_gui_1s)
        timer.start(1000)

    @pyqtSlot()
    def slot_write_config_to_gui(self):
        self.write_config_to_gui()

    @pyqtSlot()
    def slot_raw_order_update(self):
        self.update_orders_table()

    @pyqtSlot()
    def slot_update_trade_table(self):
        self.update_trade_table()

    @pyqtSlot()
    def slot_start_timers(self):
        self.start_timers()

    @pyqtSlot(str)
    def slot_trade_history_updated(self, folder_path):

        # Formerly (now deprecated) this would present a link to a single excel file (file_path) that contain the trade
        # history for all accounts in a single file.  It now just links to the parent folder, which contains
        # a separate CSV for each account.

        self.trades_tab.trade_history_link.setText(f'<a href="#">Trade History Folder</a>')
        # self.trades_tab.trade_history_link.setText(f'<a href="#">{os.path.basename(file_path)}</a>')
        self.trades_tab.trade_history_link.setOpenExternalLinks(False)
        self.trades_tab.trade_history_link.linkActivated.connect(lambda:
                                        QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path)))
        self.trades_tab.trade_history_link.show()

    @pyqtSlot(tuple)
    def slot_exception_handling(self, exception_tuple):
        # This only handles EXCEPTIONS, instead of raising exceptions, they are handled as per levels below.

        level = exception_tuple[0]
        error_text = exception_tuple[1]
        stop_oms = exception_tuple[2]
        trace = exception_tuple[3]

        if type(error_text) == list:
            error_text = error_text[0]

        self.oms._stop_signal = stop_oms

        if level == 1:
            # Critical Error - unhandled error that stops the program working

            # Save Stack Trace
            error_time = datetime.strftime(datetime.now(), "%Y-%m-%d %H%M%S")
            trace_file_name = f'STACK TRACE {error_time}.txt'
            trace_file_path = os.path.join(ADDR.folder_stack_traces, trace_file_name)
            with open(trace_file_path, 'a') as f:
                f.write(f'Error Time (market): {US_MARKET.current_time}\n')
                f.write(f'Error Time (local): {error_time}\n\n')
                f.write('ERROR TRACEBACK:\n')
                f.write(error_text + '\n')
                f.write('\n\nFull trace:\n')
                for fs in trace:
                    f.write(str(fs) + '\n')
            self.show_error_message(error_message=f'An unhandled error has occurred:\n\n'
                                                  f'{error_text}\n\n'
                                                  f'Error Location: {trace[-2]}\n\n'
                                                  f'A trace file has been saved at:\n'
                                                  f'{trace_file_path}\n\n'
                                                  f'Please pass the trace file to the developer.',
                                    error_title='CRITICAL ERROR')
            self.oms.shutdown()
            self.close()
            sys.exit()
        elif level == 2:
            # Error - anticipated error that stops the program working
            self.logger.error(error_text)
            self.oms_tab.button_restart_oms.show()
        elif level == 3:
            # Warning/Alert - anticipated error tha doesn't stop the program working
            self.logger.warning(error_text)
        elif level == 4:
            # Info - normal operations
            self.logger.info(error_text)
        elif level == 5:
            self.logger.debug(error_text)
        else:
            self.show_error_message(error_message=f'An unidentifiable error has occurred:\n\n{error_text}\n\n'
                                                  f'Please note this error and pass it to the developer.',
                                    error_title='UNIDENTIFIED ERROR')
            sys.exit()

    def restart_oms(self):
        # called by the user manually (pushbutton) after an error has stopped the oms
        self.oms_tab.button_restart_oms.hide()
        self.logger.info('OMS restarted by user')

        # restart OMS
        self.oms._stop_signal = False

        # restart email handler(s)
        for smtp_handler in [h for h in self.logger.handlers if type(h) == customSMTPHandler]:
            # Deprecated
            smtp_handler._stop_signal = False
        EMAIL_MANAGER._stop_signal = False  # replaces smtp_handlers above

    @pyqtSlot(logging.LogRecord)
    def slot_update_log(self, record):
        record.message = record.message.split('\n')
        self.log_table_queue.append(record)
        self.add_to_table()

    def add_to_table(self):
        with self.gui_lock:
            record = self.log_table_queue.pop(0)
            messages = record.message
            for m in [m[:500] for m in messages if m]:
                row_id = self.log_table.rowCount()
                self.log_table.setRowCount(row_id + 1)
                item_time = QTableWidgetItem(record.asctime)
                item_time.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item_level = QTableWidgetItem(record.levelname)
                item_level.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                item_msg = QTableWidgetItem(m)
                item_msg.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if record.levelname in ['WARNING', 'ERROR', 'CRITICAL']:
                    item_time.setForeground(QBrush(QColor(Qt.GlobalColor.red)))
                    item_level.setForeground(QBrush(QColor(Qt.GlobalColor.red)))
                    item_msg.setForeground(QBrush(QColor(Qt.GlobalColor.red)))
                self.log_table.setItem(row_id, 0, item_time)
                self.log_table.setItem(row_id, 1, item_level)
                self.log_table.setItem(row_id, 2, item_msg)
            # set column widths
            self.log_table.resizeColumnToContents(2)
            self.log_table.setColumnWidth(2, self.log_table.columnWidth(2) + 10)
            self.log_table.scrollToBottom()

    def start_timers(self):

        # TODO: This belongs in the oms.py module.  No need for it to be in gui code.

        self.logger.debug('start_timers')

        self.daily_report_timer.start((self.oms.calc_target_time(datetime.now().date() - timedelta(days=1),
                                                                 self.oms.config['Daily Report Time']) -
                                       US_MARKET.current_time).seconds * 1000)
        self.rt_output_timer.start((self.oms.calc_target_time(datetime.now().date() - timedelta(days=1),
                                                              self.oms.config['RT Output File Time']) -
                                    US_MARKET.current_time).seconds * 1000)

    def daily_report(self, reset_timer=True):

        self.logger.debug('gui.daily_report')
        if self.oms._stop_signal:
            return

        daily_report_thread = threading.Thread(target=self.oms.issue_daily_reports, name='Daily Report Thread')
        daily_report_thread.start()

        if reset_timer:
            with self.gui_lock:
                current_time = US_MARKET.current_time
                target_time = self.oms.calc_target_time(current_time.date(), self.oms.config['Daily Report Time'])
                remaining = target_time - current_time
                remaining = (86400 * remaining.days + remaining.seconds) * 1000
                self.daily_report_timer.setInterval(remaining)

    def rt_output_file(self, reset_timer=True):
        # reset_timer:  when this function is called manually by the user (via the "Generate RT Files Now" button),
        #   the daily timer is unaffected - i.e. the RT file is always generated at that scheduled daily time,
        #   irrespective of whether the user has manually generated it in between.

        self.logger.debug('gui.rt_output_file')
        if self.oms._stop_signal:
            return

        rt_output_thread = threading.Thread(target=self.oms.issue_rt_trade_list, name='RT Output Thread')
        rt_output_thread.start()

        if reset_timer:
            with self.gui_lock:
                current_time = US_MARKET.current_time
                target_time = self.oms.calc_target_time(current_time.date(), self.oms.config['RT Output File Time'])
                remaining = target_time - current_time
                remaining = (86400 * remaining.days + remaining.seconds) * 1000
                self.rt_output_timer.setInterval(remaining)

    @staticmethod
    def call_function_in_thread(function_name, thread_name, args=()):
        thread = threading.Thread(target=function_name, args=args, name=thread_name)
        thread.start()

    def update_gui_1s(self):

        # TODO: this is legacy code - replace with updates triggered by SIGNALS emissions.

        init_text = 'Initialising OMS connections...'

        with self.gui_lock:
            # market clock
            if self.oms._stop_signal:
                self.header_oms_status.show()
                self.oms_tab.market_clock.setText('Error - OMS stopped')
                self.oms_tab.dr_timer_label.setText('Daily Reports stopped')
                self.oms_tab.rt_timer_label.setText('RT Output Files stopped')
                return

            self.oms_tab.rt_button.setVisible(self.oms.initialised)
            self.oms_tab.dr_button.setVisible(self.oms.initialised)

            self.header_oms_status.hide()  # hide error bar

            self.oms_tab.market_clock.setText("NYSE " +
                                              datetime.strftime(US_MARKET.current_time, '%a %e %b %Y') + '\n'+
                                              datetime.strftime(US_MARKET.current_time, '%#I:%M:%S %p')) \
                if US_MARKET else init_text

            # daily report countdown
            if not self.oms.initialised:
                self.oms_tab.dr_timer_label.setText(init_text)
            elif self.oms._reporting_lock.locked() and self.oms._blocking_function == 'daily_reports':
                current_text = self.oms_tab.dr_timer_label.text()
                label = current_text + "." if len(current_text) < 27 else 'Generating daily reports'
                self.oms_tab.dr_timer_label.setText(label)
            else:
                self.oms_tab.dr_timer_label.setText('Next Daily Report in ' +
                    utilities.timer_display_text(self.daily_report_timer.remainingTime() / 1000))

            # RealTest output countdown
            if not self.oms.initialised:
                self.oms_tab.rt_timer_label.setText('')
            elif self.oms._reporting_lock.locked() and self.oms._blocking_function == 'rt_output':
                current_text = self.oms_tab.rt_timer_label.text()
                label = current_text + "." if len(current_text) < 28 else 'Generating RealTest Files'
                self.oms_tab.rt_timer_label.setText(label)
            else:
                self.oms_tab.rt_timer_label.setText(
                    'Next RT Output Files in ' +
                    utilities.timer_display_text(self.rt_output_timer.remainingTime() / 1000))

            # orders next sent in
            if not self.oms.initialised:
                self.orders_tab.order_window_help_text.setText(init_text)
                self.oms_tab.orders_timer_label.setText('')

            elif self.oms.order_processing_status:
                self.oms_tab.orders_timer_label.setText(self.oms.order_processing_status)
                self.orders_tab.order_window_help_text.setText(self.oms.order_processing_status)

            elif OMS_SETTINGS.process_orders_basis == 'SCHEDULED':
                if self.oms.is_time_to_process_orders():
                    self.oms_tab.orders_timer_label.setText(f"1 minute order-loading window currently active.")
                    self.orders_tab.order_window_help_text.setText(
                        f"1 minute order-loading window active.")
                else:
                    remaining = 0
                    if self.oms.scheduled_order_time:
                        remaining = (self.oms.scheduled_order_time - US_MARKET.current_time)
                        remaining = remaining.days*86400 + remaining.seconds
                    if remaining > 0:
                        self.oms_tab.orders_timer_label.setText(f'Orders: scheduled start in '
                                                                f'{utilities.timer_display_text(remaining)}')

                        # Scheduled time strings:
                        st = OMS_SETTINGS.scheduled_order_processing_time
                        st1 = st.strftime("%H:%M")
                        st2 = (datetime.combine(datetime.today(), st) + timedelta(hours=1)).time().strftime('%H:%M')
                        st3 = (datetime.combine(datetime.today(), st) + timedelta(hours=2)).time().strftime('%H:%M')
                        window_strings = f'{st1}, {st2} and {st3}'
                        self.orders_tab.order_window_help_text.setText(
                            f"Orders will be automatically processed in 1 minute windows "
                            f"starting at {window_strings}, market time. To process orders outside of "
                            f"these times, use the 'Send Orders Now' button. \n\n"
                            f"Next orders processed in {utilities.timer_display_text(remaining)}.")
                    else:
                        if self.oms.scheduled_order_time:
                            self.oms_tab.orders_timer_label.setText(f'Orders: scheduled '
                                        f'{datetime.strftime(self.oms.scheduled_order_time, "%H:%M")}')
                        else:
                            self.oms_tab.orders_timer_label.setText(f'Orders: Scheduled')
            else:
                self.oms_tab.orders_timer_label.setText(f'Orders must be sent manually')
                self.orders_tab.order_window_help_text.setText(f"Click the the 'Send Orders Now' button to send "
                                                               f"orders, or set order basis to Scheduled.")

        # account connection statuses
        self.update_connection_status_widgets()

    def closeEvent(self, event):
        # overrides window closure, to ensure orderly shutdown of OMS
        # if not self.oms.force_exit:
        reply = QMessageBox.question(self, 'Shutting down', "Are you sure?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.logger.info('Shutting down...')
            self.oms.shutdown()
            event.accept()
            self.logger.info('Shut down complete')
            sys.exit()
        else:
            event.ignore()
        # else:
        #     event.accept()

    @staticmethod
    def show_error_message(error_message, error_title='Error'):
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Icon.Critical)
        error_box.setText(error_message)
        error_box.setWindowTitle(error_title)
        error_box.raise_()
        error_box.activateWindow()
        error_box.exec()

    def create_oms_tab(self):

        # create tab widget
        self.oms_tab.widget = QWidget()

        # market clock
        self.oms_tab.market_clock = QLabel('Connecting...')
        self.oms_tab.market_clock.setFont(QFont(QApplication.font().family(), 16))
        self.oms_tab.market_clock.font().setBold(True)
        self.oms_tab.market_clock.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # create account connection status layout
        connections_groupbox = QGroupBox('Account Connection Status')
        connections_groupbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.oms_tab.connections_groupbox_layout = QVBoxLayout()
        self.oms_tab.connections_groupbox_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        connections_groupbox.setLayout(self.oms_tab.connections_groupbox_layout)

        # create daily reports and RT output timers
        daily_reports_groupbox = QGroupBox('Daily Outputs')
        self.oms_tab.dr_timer_label = QLabel('Next Daily Report in ')
        self.oms_tab.rt_timer_label = QLabel('Next RT Output Files in ')
        self.oms_tab.orders_timer_label = QLabel('Orders: automatically sent in ')
        self.oms_tab.orders_timer_label.setWordWrap(True)
        self.oms_tab.dr_button = QPushButton('Generate Daily Report Now')
        self.oms_tab.dr_button.setDefault(True)
        # noinspection PyUnresolvedReferences
        self.oms_tab.dr_button.clicked.connect(lambda: self.daily_report(reset_timer=False))
        self.oms_tab.rt_button = QPushButton('Generate RT Files Now')
        self.oms_tab.rt_button.setDefault(True)
        # noinspection PyUnresolvedReferences
        self.oms_tab.rt_button.clicked.connect(lambda: self.rt_output_file(reset_timer=False))
        daily_reports_layout = QVBoxLayout()
        daily_reports_layout.addWidget(self.oms_tab.dr_timer_label)
        daily_reports_layout.addWidget(self.oms_tab.dr_button)
        daily_reports_layout.addWidget(self.oms_tab.rt_timer_label)
        daily_reports_layout.addWidget(self.oms_tab.rt_button)
        daily_reports_layout.addWidget(self.oms_tab.orders_timer_label)
        daily_reports_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        daily_reports_groupbox.setLayout(daily_reports_layout)

        # create OMS Stopped alert
        self.oms_tab.button_restart_oms = QPushButton('Restart OMS')
        self.oms_tab.button_restart_oms.hide()
        # noinspection PyUnresolvedReferences
        self.oms_tab.button_restart_oms.clicked.connect(self.restart_oms)

        # create oms log layout
        log_hbox = QHBoxLayout()
        log_hbox.setContentsMargins(5, 5, 5, 5)
        log_hbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        # noinspection PyUnresolvedReferences
        log_hbox.addWidget(self.log_table)

        # settings layout
        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.oms_tab.market_clock)
        settings_layout.addWidget(self.oms_tab.button_restart_oms)
        settings_layout.addWidget(connections_groupbox)
        settings_layout.addWidget(daily_reports_groupbox)
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # add layouts
        left_bar_width_widget = QWidget()
        left_bar_width_widget.setMinimumWidth(self.left_bar_width)
        left_bar_width_widget.setMaximumWidth(self.left_bar_width)
        left_bar_width_widget.setLayout(settings_layout)
        self.oms_tab.oms_layout = QHBoxLayout()
        self.oms_tab.oms_layout.setContentsMargins(5, 5, 5, 5)
        self.oms_tab.oms_layout.addWidget(left_bar_width_widget)
        self.oms_tab.oms_layout.addLayout(log_hbox)
        self.oms_tab.oms_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.oms_tab.widget.setLayout(self.oms_tab.oms_layout)
        self.tab_widget.addTab(self.oms_tab.widget, "OMS")
        self.logger.info(f'Welcome to the Quantive Alpha Order Management System v{self.oms.version}')
        self.update_connection_status_widgets()

    def update_connection_status_widgets(self):

        # self.logger.debug('Account connection update')

        with self.gui_lock:
            connections_layout = self.oms_tab.connections_groupbox_layout
            for a in self.oms.trading_accounts:
                found_widget = None
                for i in range(connections_layout.count()):
                    item = connections_layout.itemAt(i)
                    if item.widget() and item.widget().objectName() == f'{a.alias} ({a.id})':
                        found_widget = item.widget()

                try:
                    if a.ib_type == 'MANAGED':
                        broker = [b for b in self.oms.brokers if a.id in b.api.connected_accounts][0]
                    else:
                        broker = [b for b in self.oms.brokers if b.api.account_id == a.id][0]
                    if broker.api.connState == 0:
                        connection_colour = global_red  # disconnected
                    elif broker.api.connState == 1:
                        connection_colour = global_orange  # connecting
                    elif broker.api.connState == 2:
                        connection_colour = global_green  # connected
                    elif broker.api.connState == 3:
                        connection_colour = global_blue  # redirect  (not sure what this one is)
                    else:
                        connection_colour = global_grey_text
                except IndexError:
                    connection_colour = global_grey_text
                connection_text = f"<font color='{connection_colour}'>{a.alias} ({a.id})</font>"

                if found_widget:
                    found_widget.setText(connection_text)
                else:
                    account_label = QLabel(connection_text)
                    account_label.setObjectName(f'{a.alias} ({a.id})')
                    account_label.setAlignment(Qt.AlignmentFlag.AlignTop)
                    connections_layout.addWidget(account_label)

    def create_trades_tab(self):

        self.trades_tab.trades_table = QTableWidget()
        self.trades_tab.trades_table.setAlternatingRowColors(True)
        self.trades_tab.report_columns = ['account_id', 'strategy.qa_strategy_model', 'ticker',
                                          'entry_datetime', 'status', 'order_price', 'avg_entry_price', 'order_size',
                                          'achieved_entry_size', 'entry_value', 'current_price', 'exit_datetime',
                                          'avg_exit_price', 'exit_type', 'unrealised_pnl', 'net_pnl', 'brokerage',
                                          'trade_id'
                                          ]

        # create Trade tab
        self.trades_tab.tab_widget = QWidget()
        self.trades_tab.tab_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)

        # create Trade tab settings widget

        #  Settings - Account(s) to show
        self.trades_tab.account_picker = QComboBox()
        self.trades_tab.account_picker.addItems([f'{a.alias} ({a.id})' for a in self.oms.trading_accounts])
        self.trades_tab.account_picker.currentIndexChanged.connect(self.update_trade_table)

        #  Settings - Date Range
        self.trades_tab.range_picker = QComboBox()
        self.trades_tab.range_picker.addItems(['Last Session', '7 Days', 'This Month', 'Last Month',
                                               'This FY', 'All Time', 'Custom'])
        self.trades_tab.range_picker.currentIndexChanged.connect(self.trades_range_picker_changed)

        #  Settings - Custom Date Range
        self.trades_tab.trades_start_date_picker = QDateEdit()
        self.trades_tab.trades_end_date_picker = QDateEdit()
        self.trades_tab.trades_start_date_picker.setDisplayFormat("yyyy-MM-dd")
        self.trades_tab.trades_start_date_picker.setDate((datetime.now() - timedelta(days=7)).date())
        self.trades_tab.trades_start_date_picker.dateChanged.connect(self.update_trade_table)
        self.trades_tab.trades_start_date_label = QLabel('Start Date')
        self.trades_tab.trades_start_date_label.setBuddy(self.trades_tab.trades_start_date_picker)

        self.trades_tab.trades_end_date_picker.setDisplayFormat("yyyy-MM-dd")
        self.trades_tab.trades_end_date_picker.setDate(datetime.now().date())
        self.trades_tab.trades_end_date_picker.dateChanged.connect(self.update_trade_table)
        self.trades_tab.trades_end_date_label = QLabel('End Date')
        self.trades_tab.trades_end_date_label.setBuddy(self.trades_tab.trades_end_date_picker)

        self.trades_tab.trades_start_date_picker.hide()
        self.trades_tab.trades_end_date_picker.hide()
        self.trades_tab.trades_start_date_label.hide()
        self.trades_tab.trades_end_date_label.hide()

        #  Settings - What to Show
        show_group = QGroupBox('What to Show')
        # show_group.setExclusive(False)  # allow multiple items to be selected
        self.trades_tab.show_open_trades = QCheckBox('Open Trades')
        self.trades_tab.show_completed_trades = QCheckBox('Completed Trades')
        self.trades_tab.show_placed_trades = QCheckBox('Placed Orders')
        for checkbox in [self.trades_tab.show_open_trades, self.trades_tab.show_completed_trades,
                         self.trades_tab.show_placed_trades]:
            checkbox.stateChanged.connect(self.update_trade_table)
            checkbox.setChecked(True)

        # Settings - Delete a Trade
        self.trades_tab.delete_a_trade_button = QPushButton('Delete a Trade')
        self.trades_tab.delete_a_trade_button.clicked.connect(self.delete_a_trade)  # type: ignore

        # Settings - Flush Cancelled Trades
        self.trades_tab.delete_cancelled_trades = QPushButton('Archive Old Trades')
        self.trades_tab.delete_cancelled_trades.clicked.connect(self.archive_old_trades)  # type: ignore

        # Settings - Download All Trades
        self.trades_tab.trade_history_link = QLabel('')
        self.trades_tab.trade_history_link.hide()
        self.trades_tab.download_trades = QPushButton('Export Full Trade History')
        self.trades_tab.download_trades.clicked.connect(lambda:
                                                        self.trades_tab.trade_history_link.setText('Generating...'))
        self.trades_tab.download_trades.clicked.connect(lambda:
                                                        self.trades_tab.trade_history_link.show())
        self.trades_tab.download_trades.clicked.connect(lambda:
                                        self.call_function_in_thread(self.oms.export_trade_history,
                                                                     'Trade History Export'))

        # create Layout
        form_layout = QFormLayout()
        form_layout.addRow(QLabel('Account'), self.trades_tab.account_picker)
        form_layout.addRow(QLabel('Display Range'), self.trades_tab.range_picker)
        form_layout.addRow(self.trades_tab.trades_start_date_label, self.trades_tab.trades_start_date_picker)
        form_layout.addRow(self.trades_tab.trades_end_date_label, self.trades_tab.trades_end_date_picker)
        form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setContentsMargins(10, 5, 20, 5)
        group_box_layout = QVBoxLayout()
        group_box_layout.addWidget(self.trades_tab.show_open_trades)
        group_box_layout.addWidget(self.trades_tab.show_completed_trades)
        group_box_layout.addWidget(self.trades_tab.show_placed_trades)
        group_box_layout.setContentsMargins(10, 5, 20, 5)
        group_box_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        show_group.setLayout(group_box_layout)
        settings_layout = QVBoxLayout()
        settings_layout.addLayout(form_layout)
        settings_layout.addWidget(show_group)
        settings_layout.addWidget(self.trades_tab.download_trades)
        settings_layout.addWidget(self.trades_tab.delete_a_trade_button)
        settings_layout.addWidget(self.trades_tab.delete_cancelled_trades)
        settings_layout.addWidget(self.trades_tab.trade_history_link)
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        left_bar_width_widget = QWidget()
        left_bar_width_widget.setMinimumWidth(self.left_bar_width)
        left_bar_width_widget.setMaximumWidth(self.left_bar_width)
        left_bar_width_widget.setLayout(settings_layout)
        tab1hbox = QHBoxLayout()
        tab1hbox.setContentsMargins(5, 5, 5, 5)
        tab1hbox.addWidget(left_bar_width_widget)
        tab1hbox.addWidget(self.trades_tab.trades_table)
        self.trades_tab.tab_widget.setLayout(tab1hbox)

        self.tab_widget.addTab(self.trades_tab.tab_widget, "Trade History")

        # Update with data
        self.update_trade_table()

    def update_accounts_list(self):

        for tab in [self.trades_tab, self.orders_tab]:
            tab.account_picker.clear()
            tab.account_picker.addItems(['All'] + [f'{a.alias} ({a.id})' for a in self.oms.trading_accounts])
            # other items may be added here later as needed when an account is added/changes

    def trades_range_picker_changed(self):

        if self.trades_tab.range_picker.currentText() == 'Custom':
            with self.gui_lock:
                self.trades_tab.trades_start_date_picker.show()
                self.trades_tab.trades_end_date_picker.show()
                self.trades_tab.trades_start_date_label.show()
                self.trades_tab.trades_end_date_label.show()
        else:
            with self.gui_lock:
                self.trades_tab.trades_start_date_picker.hide()
                self.trades_tab.trades_end_date_picker.hide()
                self.trades_tab.trades_start_date_label.hide()
                self.trades_tab.trades_end_date_label.hide()
            self.update_trade_table()

    def delete_a_trade(self):
        trade_number, ok_pressed = QInputDialog.getInt(self, "Delete Trade", "Enter trade number for deletion:")
        if ok_pressed:
            # find related trade register
            found_trade = None
            for b in self.oms.brokers:
                if not found_trade:
                    for tr in b.api.trade_registers:
                        found_trade = [t for t in tr.trades if t.trade_id == trade_number]
                        if found_trade:
                            found_trade = found_trade[0]
                            confirmation = QMessageBox.question(self, "Confirmation",
                                                                f"Delete:\n\n"
                                                                f"Trade {found_trade.trade_id} \n\n"
                                                                f"from account {found_trade.account_id}.\n\n"
                                                                f"This will irreversibly delete the trade from the "
                                                                f"account trade register.\n\n"
                                                                f"Are you sure?\n\n",
                                                                QMessageBox.StandardButton.Yes |
                                                                QMessageBox.StandardButton.No,
                                                                QMessageBox.StandardButton.No)
                            if confirmation == QMessageBox.StandardButton.Yes:
                                tr.trades.remove(found_trade)
                                tr.save_trade_list()
                                self.update_trade_table()
                                break

    def archive_old_trades(self):
        # this allows the user to delete cancelled trades and compress completed trades from the trade register file.
        # Cancelled trades are trades which are not place (for various reasons) or placed but entry limits not
        # penetrated before expiry.  See trades.prune() function for archiving approach.

        from src.client.broker import BrokerApp
        found = False
        for b in self.oms.brokers:
            assert isinstance(b, BrokerApp)
            for tr in b.api.trade_registers:

                if len(tr.trades) == 0:
                    continue

                # Data integrity check before deletion.  TODO: Migrate check to trade register object.
                if (len(list(set([t.account_id for t in tr.trades]))) > 1 or
                        len(list(set([t.account_alias for t in tr.trades]))) > 1):
                    # Data integrity check
                    msg_box = QMessageBox()
                    msg_box.setWindowTitle("Trade Register Error")
                    msg_box.setText(
                        f"Trade register contains multiple accounts "
                        f"{list(set([t.account_id for t in tr.trades]))} "
                        f"{list(set([t.account_alias for t in tr.trades]))} - contact "
                        f"the developer.\n\n"
                        f"Cancelled trades cannot be deleted."
                    )
                    msg_box.exec()

                # Get User Confirmation
                cancelled_trades = [t for t in tr.trades if
                                    t.status == 'CANCELLED' and
                                    t.created_datetime and
                                    t.created_datetime.replace(tzinfo=None) < datetime.now() - timedelta(days=7)]
                complete_trades = [t for t in tr.trades if
                                   t.status == 'COMPLETE' and
                                   t.exit_datetime and
                                   t.exit_datetime.replace(tzinfo=None) < datetime.now() - timedelta(days=7)]

                if not cancelled_trades and not complete_trades:
                    continue

                found = True

                nlc = '\n • '
                alias = tr.trades[0].account_alias
                statuses = list(set([t.status for t in tr.trades]))
                status_summary = [f'{s} - {len([t for t in tr.trades if t.status == s])} trades' for s in statuses]
                confirmation = QMessageBox.question(self, "Confirmation",
                                                    f"{alias} Trade Register, current data:\n\n"
                                                    f" • {nlc.join(status_summary)}"
                                                    f"\n\nClick Yes to reduce trade register size. This will delete "
                                                    f"{len(cancelled_trades)} cancelled trades greater than 7 days "
                                                    f"old, and remove "
                                                    f"secondary data from {len(complete_trades)} completed trades "
                                                    f"greater than 7 days old."
                                                    f"\n\nThis cannot be undone.\n\n" 
                                                    f"Are you sure?\n\n",
                                                    QMessageBox.StandardButton.Yes |
                                                    QMessageBox.StandardButton.No,
                                                    QMessageBox.StandardButton.No)

                # reduce trade data
                if confirmation == QMessageBox.StandardButton.Yes:

                    prior_size = round(tr.get_file_size_mb(), 1)

                    msg_box = QMessageBox()
                    msg_box.setWindowTitle("Archiving")
                    msg_box.setText(f"{alias} Trade Register is being archived\n\n")
                    msg_box.show()

                    tr.trades = [t for t in tr.trades if t not in cancelled_trades]
                    for t in complete_trades:
                        t.prune()

                    tr.save_trade_list()
                    msg_box.hide()

                    # Notify user of size reduction
                    new_size = round(tr.get_file_size_mb(), 1)
                    msg_box = QMessageBox()
                    msg_box.setWindowTitle("Success")
                    msg_box.setText(f"{alias} Trade Register file size reduced:\n"
                                    f"Original Size = {prior_size} MB\n"
                                    f"Reduced Size = {new_size} MB\n\n")
                    msg_box.exec()

        self.update_trade_table()

        if not found:
            msg_box = QMessageBox()
            msg_box.setWindowTitle("No Cancelled Trades")
            msg_box.setText("No cancelled trades were found in any trade register.")
            msg_box.exec()

    def update_trade_table(self):

        with self.gui_lock:
            # get date range selected by user
            last_session = datetime(2000, 1, 1).date()
            for b in self.oms.brokers:
                for tr in b.api.trade_registers:
                    try:
                        if tr.trades:
                            last_session = max(max(
                                max([t.created_datetime for t in tr.trades]),
                                max([tr.trades[0].created_datetime] + [t.entry_datetime
                                                                       for t in tr.trades
                                                                       if t.entry_datetime]),
                                max([tr.trades[0].created_datetime] + [t.exit_datetime
                                                                       for t in tr.trades
                                                                       if t.exit_datetime])).date(),
                                               last_session)
                    except ValueError:
                        pass

            end_date = last_session
            range_setting = self.trades_tab.range_picker.currentText()
            if range_setting == 'Last Session':
                start_date = last_session
            elif range_setting == '7 Days':
                start_date = last_session - timedelta(days=7)
            elif range_setting == 'This Month':
                start_date = end_date.replace(day=1)
            elif range_setting == 'Last Month':
                end_date = end_date.replace(day=1) - timedelta(days=1)
                start_date = end_date.replace(day=1)
            elif range_setting == 'This FY':
                if last_session.month < 7:
                    start_date = datetime(last_session.year - 1, 7, 1).date()
                else:
                    start_date = datetime(last_session.year, 7, 1).date()
            elif range_setting == 'All Time':
                start_date = datetime(2000, 1, 1).date()
            elif range_setting == 'Custom':
                start_date = self.trades_tab.trades_start_date_picker.date().toPyDate()
                end_date = self.trades_tab.trades_end_date_picker.date().toPyDate()
            else:
                raise ValueError('Unknown Range Dates')

            # get "show items" settings
            status_to_show = []
            if self.trades_tab.show_open_trades.isChecked():
                status_to_show.append('OPEN')
            if self.trades_tab.show_completed_trades.isChecked():
                status_to_show.append('COMPLETE')
            if self.trades_tab.show_placed_trades.isChecked():
                status_to_show.extend(['PLACED', 'DRAFT'])

            # get trades for selected account(s)
            account = self.trades_tab.account_picker.currentText()
            accounts = [a for a in self.oms.trading_accounts if account == f'{a.alias} ({a.id})' or account == 'All']
            trades = []
            for a in accounts:
                for b in self.oms.brokers:
                    for tr in b.api.trade_registers:
                        if tr.account_id == a.id:
                            trades = trades + tr.trades

            trades_for_screen = [t for t in trades
                                 if t.status in status_to_show
                                 and (t.status == 'PLACED' or
                                      ((t.exit_datetime or t.entry_datetime) and
                                       ((t.exit_datetime and start_date <= t.exit_datetime.date() <= end_date) or
                                        (t.entry_datetime and start_date <= t.entry_datetime.date() <= end_date)))
                                      )]
            trades_for_screen.sort(key=lambda x: (x.entry_datetime is None, x.entry_datetime), reverse=True)

            # delete existing items (to free up memory)
            self.delete_all_table_items(self.trades_tab.trades_table)

            # add new items
            if trades_for_screen:
                table_headers = [trades_for_screen[0].report_parameter(p).column_header
                                 for p in self.trades_tab.report_columns]

                # set row count
                self.trades_tab.trades_table.clearContents()
                self.trades_tab.trades_table.setRowCount(len(trades_for_screen) + 1)
                self.trades_tab.trades_table.setColumnCount(len(self.trades_tab.report_columns))

                # add trade data to table
                pnl_col = table_headers.index('Net PnL')
                for idx, trade in enumerate(trades_for_screen):
                    parameters = [trade.report_parameter(p) for p in self.trades_tab.report_columns]
                    for c, parameter in enumerate(parameters):
                        data_point = QTableWidgetItem(parameter.formatted_string_value)
                        if parameter.align == 'right':
                            alignment = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        elif parameter.align == 'centre':
                            alignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                        elif parameter.align == 'left':
                            alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                        else:
                            alignment = Qt.AlignmentFlag.AlignVCenter
                        data_point.setTextAlignment(alignment)

                        if parameter.string_value:
                            data_point.setToolTip(parameter.string_value)
                        self.trades_tab.trades_table.setItem(idx, c, data_point)

                total_net_pnl = str(round(sum([t.net_pnl for t in trades_for_screen]), 2))
                total_u_pnl = str(round(sum([t.unrealised_pnl for t in trades_for_screen]), 2))
                pnl_data_point = QTableWidgetItem(str(total_net_pnl))
                pnl_data_point.setTextAlignment(Qt.AlignmentFlag.AlignRight)
                upnl_data_point = QTableWidgetItem(str(total_u_pnl))
                upnl_data_point.setTextAlignment(Qt.AlignmentFlag.AlignRight)
                self.trades_tab.trades_table.setItem(self.trades_tab.trades_table.rowCount() - 1, pnl_col, pnl_data_point)
                self.trades_tab.trades_table.setItem(self.trades_tab.trades_table.rowCount() - 1, pnl_col - 1,
                                                     upnl_data_point)
                self.trades_tab.trades_table.setItem(self.trades_tab.trades_table.rowCount() - 1, pnl_col - 2,
                                                     QTableWidgetItem('TOTAL PnL'))

                # colour code PnL
                for r in range(self.trades_tab.trades_table.rowCount()):
                    for col in [pnl_col, pnl_col - 1]:
                        pnl_item = self.trades_tab.trades_table.item(r, col)
                        if pnl_item:
                            try:
                                if float(pnl_item.text()) < 0:
                                    pnl_item.setForeground(QBrush(QColor(Qt.GlobalColor.red)))
                                elif float(pnl_item.text()) > 0:
                                    pnl_item.setForeground(QBrush(QColor(Qt.GlobalColor.darkGreen)))
                            except ValueError:
                                pass

                self.trades_tab.trades_table.setHorizontalHeaderLabels(table_headers)
                self.trades_tab.trades_table.horizontalHeader().show()

            else:
                self.trades_tab.trades_table.viewport().update()
                self.trades_tab.trades_table.verticalHeader().setVisible(False)
                self.trades_tab.trades_table.horizontalHeader().setVisible(False)
                if [b.api.trade_registers for b in self.oms.brokers]:
                    self.trades_tab.trades_table.setItem(0, 0, QTableWidgetItem('No trades found'))
                else:
                    self.trades_tab.trades_table.setItem(0, 0, QTableWidgetItem('Loading...'))

            # set column widths
            for c in range(self.trades_tab.trades_table.columnCount()):
                self.trades_tab.trades_table.resizeColumnToContents(c)
                self.trades_tab.trades_table.setColumnWidth(c, self.trades_tab.trades_table.columnWidth(c) + 10)

            self.trades_tab.trades_table.setSortingEnabled(True)  # causes issues

    def create_orders_tab(self):

        self.orders_tab.orders_table = QTableWidget()
        self.orders_tab.orders_table.setAlternatingRowColors(True)

        # create Orders tab
        self.orders_tab.tab_widget = QWidget()
        self.orders_tab.tab_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)

        # create Orders tab settings widget

        #  Settings - Account(s) to show
        self.orders_tab.account_picker = QComboBox()
        self.orders_tab.account_picker.addItems([f'{a.alias} ({a.id})' for a in self.oms.trading_accounts])
        self.orders_tab.account_picker.currentIndexChanged.connect(self.update_orders_table)

        #  Settings - What to Show
        show_group = QGroupBox('What to Show')
        # ['PENDING', 'PROCESSING', 'PLACED', 'REJECTED', 'INVALID']
        self.orders_tab.show_pending_orders = QCheckBox('Pending')
        self.orders_tab.show_placed_orders = QCheckBox('Placed')
        self.orders_tab.show_rejected_orders = QCheckBox('Rejected')
        self.orders_tab.show_invalid_orders = QCheckBox('Invalid')
        for checkbox in [self.orders_tab.show_pending_orders, self.orders_tab.show_placed_orders,
                         self.orders_tab.show_rejected_orders,self.orders_tab.show_invalid_orders ]:
            checkbox.stateChanged.connect(self.update_orders_table)
            checkbox.setChecked(True)

        # Settings - Order Processing
        processing_group = QGroupBox('Order Processing')
        self.orders_tab.process_time = QTimeEdit()
        self.orders_tab.process_time.setTime(QTime(OMS_SETTINGS.scheduled_order_processing_time))
        self.orders_tab.process_time.timeChanged.connect(lambda: OMS_SETTINGS.update_serialised_settings(
            {'scheduled_order_processing_time': self.orders_tab.process_time.time().toPyTime()}))
        self.orders_tab.process_time_label = QLabel('Scheduled Time')
        self.orders_tab.process_how = QComboBox()
        self.orders_tab.process_how.addItems(['Scheduled', 'Manual'])
        self.orders_tab.process_how.currentTextChanged.connect(lambda: OMS_SETTINGS.update_serialised_settings(
            {'process_orders_basis': self.orders_tab.process_how.currentText().upper()}))
        self.orders_tab.process_how.setCurrentText(OMS_SETTINGS.process_orders_basis.capitalize())
        process_button = QPushButton('Send Orders Now')
        process_button.clicked.connect(lambda: setattr(self.oms, 'manual_order_process_button_clicked', True))
        window_strings = (f'{datetime.strftime(self.oms.scheduled_order_time, "%H:%M")},'
                          f'{datetime.strftime(self.oms.scheduled_order_time + timedelta(hours=1), "%H:%M")},'
                          f'{datetime.strftime(self.oms.scheduled_order_time + timedelta(hours=2), "%H:%M")}')
        self.orders_tab.order_window_help_text = QLabel(f"Orders will be automatically processed in 1 minute windows "
                                                        f"starting at {window_strings}. To process orders outside of "
                                                        f"these times, use the 'Send Orders Now' button")
        self.orders_tab.order_window_help_text.setWordWrap(True)
        self.orders_tab.order_window_help_text.setFixedHeight(150)
        self.orders_tab.process_how.currentTextChanged.connect(self.toggle_orders_schedule_info)
        order_folder_link = QLabel(f'<a href="#">Open Order Folder</a>')
        order_folder_link.setOpenExternalLinks(False)
        order_folder_link.linkActivated.connect(lambda:
            QDesktopServices.openUrl(QUrl.fromLocalFile(ADDR.folder_order_files)))
        self.toggle_orders_schedule_info()

        # Settings - Cancel ALl Orders
        cancel_orders = QPushButton('Cancel All Orders')
        cancel_orders.clicked.connect(self.cancel_all_orders)

        # create Layout
        form_layout = QFormLayout()
        form_layout.addRow(QLabel('Account'), self.orders_tab.account_picker)
        form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setContentsMargins(10, 5, 20, 5)
        group_box_layout = QVBoxLayout()
        group_box_layout.addWidget(self.orders_tab.show_pending_orders)
        group_box_layout.addWidget(self.orders_tab.show_placed_orders)
        group_box_layout.addWidget(self.orders_tab.show_rejected_orders)
        group_box_layout.addWidget(self.orders_tab.show_invalid_orders)
        group_box_layout.setContentsMargins(10, 5, 20, 5)
        group_box_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        show_group.setLayout(group_box_layout)
        processing_box_layout = QVBoxLayout()
        processing_layout = QFormLayout()
        processing_layout.addRow(QLabel('Order Timing'), self.orders_tab.process_how)
        processing_layout.addRow(self.orders_tab.process_time_label, self.orders_tab.process_time)
        processing_box_layout.addLayout(processing_layout)
        processing_box_layout.addWidget(self.orders_tab.order_window_help_text)
        processing_box_layout.addWidget(order_folder_link)
        processing_box_layout.addWidget(process_button)
        processing_box_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        processing_group.setLayout(processing_box_layout)
        settings_layout = QVBoxLayout()
        settings_layout.addLayout(form_layout)
        settings_layout.addWidget(show_group)
        settings_layout.addWidget(processing_group)
        settings_layout.addWidget(cancel_orders)
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        left_bar_width_widget = QWidget()
        left_bar_width_widget.setMinimumWidth(self.left_bar_width)
        left_bar_width_widget.setMaximumWidth(self.left_bar_width)
        left_bar_width_widget.setLayout(settings_layout)
        tab1hbox = QHBoxLayout()
        tab1hbox.setContentsMargins(5, 5, 5, 5)
        tab1hbox.addWidget(left_bar_width_widget)
        tab1hbox.addWidget(self.orders_tab.orders_table)
        self.orders_tab.tab_widget.setLayout(tab1hbox)

        self.tab_widget.addTab(self.orders_tab.tab_widget, "Orders")

        # Update with data
        self.update_orders_table()

    def toggle_orders_schedule_info(self):
        if self.orders_tab.process_how.currentText().upper() == 'SCHEDULED':
            self.orders_tab.process_time.show()
            self.orders_tab.process_time_label.show()

        else:
            self.orders_tab.process_time.hide()
            self.orders_tab.process_time_label.hide()

    def cancel_all_orders(self):
        reply = QMessageBox.question(self, 'Cancel Orders', "This will cancel ALL currently open orders (if not filled)"
                                                            " and update the trade register accordingly.  Would "
                                                            "you like to proceed?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.call_function_in_thread(self.oms.cancel_open_orders, 'Cancel Orders')
        else:
            pass

    def update_orders_table(self):

        with self.gui_lock:
            # get "show items" settings
            status_to_show = []
            if self.orders_tab.show_pending_orders.isChecked():
                status_to_show.extend(['PENDING', 'PROCESSING'])
            if self.orders_tab.show_placed_orders.isChecked():
                status_to_show.append('PLACED')
            if self.orders_tab.show_rejected_orders.isChecked():
                status_to_show.append('REJECTED')
            if self.orders_tab.show_invalid_orders.isChecked():
                status_to_show.append('INVALID')

            # get orders for selected account(s)
            account = self.orders_tab.account_picker.currentText()
            accounts = [a.id for a in self.oms.trading_accounts if (account == f'{a.alias} ({a.id})'
                                                                    or account == 'All')]

            orders_for_screen = [o for o in self.oms.raw_orders if
                                 (o.account_id in accounts or account == 'All') and
                                 o.status in status_to_show]
            if orders_for_screen:
                most_recent_date = max([o.date for o in orders_for_screen])
                orders_for_screen = [o for o in orders_for_screen if o.date == most_recent_date]
            orders_for_screen.sort(key=lambda x: (not x.is_exit, x.qa_strategy_model, x.order_rank))

            # capture existing column widths
            col_widths = []
            for c in range(self.orders_tab.orders_table.columnCount()):
                col_widths.append(self.orders_tab.orders_table.horizontalHeader().sectionSize(c))

            # delete existing items (to free up memory)
            self.delete_all_table_items(self.orders_tab.orders_table)

            table_headers = ['Status', 'Notes', 'Account', 'Symbol', 'ModelID', 'Order Date', 'Exchange', 'MaxExp',
                             'MaxNewExp', 'Action', 'Is Exit?', 'PctPosSize', 'OrderRank', 'Currency', 'Order Type',
                             'Lmt Price', 'TIF']
            alignment = ['', 'left', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '']

            # add new items
            if orders_for_screen:

                # set row count
                self.orders_tab.orders_table.clearContents()
                self.orders_tab.orders_table.setRowCount(len(orders_for_screen))
                self.orders_tab.orders_table.setColumnCount(len(table_headers))

                # add trade data to table
                for idx, o in enumerate(orders_for_screen):
                    row_data = [o.status, '\n'.join([a for a in o.alerts] + [e for e in o.errors]), o.account_id,
                                o.ticker, o.qa_strategy_model, o.date_str, o.exchange, o.max_exposure,
                                o.max_new_exposure, o.action, o.is_exit,
                                Decimal(str(round(o.pos_size_pct*100, 3)).ljust(5, '0')),
                                o.order_rank, o.currency, o.order_type, o.order_price, o.tif]
                    tool_tips = ['', '', '', '', '', '', '', '',
                                 str(o.pos_size_pct*100) if type(o.order_price) == float else '', '', '', '',
                                 str(o.order_price), '', '', '', '']
                    for c, parameter in enumerate(row_data):
                        if type(parameter) in [float, Decimal, int]:
                            parameter = str(Decimal(str(parameter)))
                        data_point = QTableWidgetItem(parameter)
                        if alignment[c] == 'left':
                            data_point.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                        else:
                            data_point.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
                        data_point.setToolTip(tool_tips[c])
                        self.orders_tab.orders_table.setItem(idx, c, data_point)

                if len(col_widths) == len(table_headers):
                    # update to existing date - restore original column widths
                    self.orders_tab.orders_table.setHorizontalHeaderLabels(table_headers)
                    for c, width in enumerate(col_widths):
                        self.orders_tab.orders_table.setColumnWidth(c, width)
                else:
                    # first time table is populated
                    self.orders_tab.orders_table.setHorizontalHeaderLabels(table_headers)
                    self.orders_tab.orders_table.horizontalHeader().show()
                    # set column widths
                    for c in range(self.orders_tab.orders_table.columnCount()):
                        item = self.orders_tab.orders_table.horizontalHeaderItem(c)
                        if item.text() == 'Notes':
                            self.orders_tab.orders_table.setColumnWidth(c, 250)
                        elif item.text() == 'Status':
                            self.orders_tab.orders_table.setColumnWidth(c, 80)
                        else:
                            self.orders_tab.orders_table.horizontalHeader(
                            ).setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)

            else:
                self.orders_tab.orders_table.viewport().update()
                self.orders_tab.orders_table.verticalHeader().setVisible(False)
                self.orders_tab.orders_table.horizontalHeader().setVisible(False)
                self.orders_tab.orders_table.setItem(0, 0, QTableWidgetItem('No orders found'))

            self.orders_tab.orders_table.setSortingEnabled(True)

    def create_config_tab(self):
        # within this tab, there are three sub tabs for Settings, Accounts and Trading Strategies
        self.config_tab.config_sub_tabs = QTabWidget()
        self.config_tab.config_sub_tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)

        # ADD SETTINGS TAB
        self.config_tab.settings_tab = QTabWidget()
        self.config_tab.settings_layout = QFormLayout()
        settings_layout = self.config_tab.settings_layout

        #  Settings - create & place settings_layout
        settings_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        settings_layout.setContentsMargins(10, 5, 20, 5)
        self.config_tab.settings_tab.setLayout(settings_layout)
        self.config_tab.config_sub_tabs.addTab(self.config_tab.settings_tab, 'Settings')

        # ADD ACCOUNTS TAB
        self.config_tab.accounts_tab = QTabWidget()
        self.config_tab.accounts_table = QTableWidget()
        accounts_table = self.config_tab.accounts_table
        accounts_table.setAlternatingRowColors(True)
        accounts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        #  Accounts - create accounts_layout
        accounts_layout = QVBoxLayout()
        accounts_layout.addWidget(accounts_table)
        accounts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        accounts_layout.setContentsMargins(10, 5, 20, 5)

        #  Accounts - add accounts_layout to accounts_layout tab
        self.config_tab.accounts_tab.setLayout(accounts_layout)

        #  Accounts - add accounts_layout tab to config_tab
        self.config_tab.config_sub_tabs.addTab(self.config_tab.accounts_tab, 'Accounts')

        # ADD STRATEGIES TAB
        self.config_tab.strategies_tab = QTabWidget()
        self.config_tab.strategies_table = QTableWidget()
        strategies_table = self.config_tab.strategies_table
        strategies_table.setAlternatingRowColors(True)

        #  Strategies - create strategies_layout
        strategies_layout = QVBoxLayout()
        strategies_layout.addWidget(strategies_table)
        strategies_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        strategies_layout.setContentsMargins(10, 5, 20, 5)

        #  Strategies - add strategies_layout to strategies_layout tab
        self.config_tab.strategies_tab.setLayout(strategies_layout)

        #  Strategies - add strategies_layout tab to config_tab
        self.config_tab.config_sub_tabs.addTab(self.config_tab.strategies_tab, 'Strategies')

        #  Finally - Write all content and add Config sub tabs to parent tab
        self.write_config_to_gui()
        self.tab_widget.addTab(self.config_tab.config_sub_tabs, 'Config')

    def write_config_to_gui(self):
        # called on startup and by the OMS whenever changes are made to the config file

        with self.gui_lock:
            settings_layout = self.config_tab.settings_layout
            accounts_table = self.config_tab.accounts_table
            strategies_table = self.config_tab.strategies_table

            # 1 - SETTINGS

            tooltips = {'Email Recipients': 'Comma separated list of email addresses'}
            for k, v in self.oms.config.items():
                if k in ['Trade Immediately with Orders File', 'Trade Start Time']:
                    # deprecated settings
                    continue
                if k in ['ToAddrs']:
                    # internal settings
                    continue
                set_v = str(v) if type(v) != str else v
                found_widget = None
                for i in range(settings_layout.count()):
                    if settings_layout.itemAt(i).widget().objectName() == k:
                        found_widget = settings_layout.itemAt(i).widget()
                if found_widget:
                    found_widget.setText(set_v)
                else:
                    settings_value = QLabel(set_v)
                    settings_value.setMaximumWidth(200)
                    settings_value.setObjectName(k)
                    settings_label = QLabel(k)
                    settings_label.setBuddy(settings_value)
                    if k in tooltips.keys():
                        settings_value.setToolTip(tooltips[k])
                        settings_label.setToolTip(tooltips[k])
                    settings_layout.addRow(settings_label, settings_value)
                    settings_layout.setAlignment(settings_value, Qt.AlignmentFlag.AlignTop)
                    settings_layout.setAlignment(settings_label, Qt.AlignmentFlag.AlignTop)

            # 2 - ACCOUNTS

            #  Accounts - get Accounts data and compile
            account_data_keys = ['id', 'ib_platform', 'ib_port', 'ib_client_id', 'ib_algo']
            ignore_keys = ['ignored_positions', 'log', 'strategy_allocations', 'alias']
            account_data_keys += [k for k in list({key for d in
                                                   [vars(a) for a in self.oms.trading_accounts] for key in d.keys()})
                                  if k not in account_data_keys
                                  and k not in ignore_keys]
            strategy_keys = [s.qa_id for s in self.oms.strategies]
            accounts_data = []
            for a in self.oms.trading_accounts:
                accounts_data += [[str(vars(a)[k]) if type(vars(a)[k]) != str else vars(a)[k] for k in account_data_keys] +
                                   [''] + [str(a.strategy_allocations[k]*100) for k in strategy_keys]]

            row_headers = [' '.join([word.capitalize() for word in key.split('_')]).replace('Ib', 'IB')
                           for key in account_data_keys] + ['Strategy Allocations (%)'] + strategy_keys
            accounts_data = [row_headers] + accounts_data

            #  Accounts - write to accounts_table widget & format table

            accounts_table.clearContents()
            accounts_table.setRowCount(len(row_headers))
            accounts_table.setColumnCount(len(accounts_data))
            salloc_row = row_headers.index('Strategy Allocations (%)')

            for r, v in enumerate(row_headers):
                for c, a in enumerate(accounts_data):
                    item_value = QTableWidgetItem(a[r])
                    item_value.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    if r == salloc_row:
                        item_value.setBackground(QColor(32, 55, 100))
                        item_value.setForeground(QColor(255, 255, 255))
                    accounts_table.setItem(r, c, item_value)
            accounts_table.setVerticalHeaderLabels(row_headers)
            accounts_table.setHorizontalHeaderLabels(['Fund Alias:'] +
                                                                     [a.alias for a in self.oms.trading_accounts])
            accounts_table.verticalHeader().hide()
            accounts_table.setSpan(salloc_row, 0, 1, len(accounts_data))

            # 3 - STRATEGIES

            strategies_table.clearContents()
            strategies_table.setRowCount(len(self.oms.strategies))
            strategies_table.setColumnCount(2)

            for r, s in enumerate(self.oms.strategies):
                strat_name_item = QTableWidgetItem(s.qa_id)
                strat_name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                direction_item = QTableWidgetItem(s.direction)
                direction_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                strategies_table.setItem(r, 0, strat_name_item)
                strategies_table.setItem(r, 1, direction_item)
            strategies_table.setHorizontalHeaderLabels(['Strategy ID', 'Direction'])
            strategies_table.verticalHeader().hide()

            # 4 - RESET REPORT TIMERS
            if US_MARKET.session_list:
                self.start_timers()

        self.update_accounts_list()

    @staticmethod
    def delete_all_table_items(table_widget: QTableWidget):

        table = table_widget
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                item_to_delete = table.item(r, c)
                del item_to_delete
        table_widget.setRowCount(1)
        table_widget.setColumnCount(1)