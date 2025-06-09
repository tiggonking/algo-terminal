# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

block_cipher = None

# Get the absolute path to the project root directory
PROJ_ROOT = os.path.abspath(os.path.dirname(__name__))

# IB API specific paths
IB_API_ROOT = os.path.join(PROJ_ROOT, 'src/ib_api/src/ibapi/IBJts/source/pythonclient')

a = Analysis(
    ['src/oms/oms.py'],
    pathex=[
        PROJ_ROOT,
        os.path.join(PROJ_ROOT, 'src'),
    ],
    binaries=[],
    datas=[
        ('src/oms/*', 'src/oms'),
        ('src/utils/*', 'src/utils'),
        ('src/broker/*', 'src/broker'),
        ('src/gui/*', 'src/gui'),
        ('src/markets/*', 'src/markets'),
        ('src/account/*', 'src/account'),
        ('src/trades/*', 'src/trades'),
        ('src/ib_api/*', 'src/ib_api'),
        ('src/config/globals/*.py', 'src/config/globals'),
        (os.path.join(IB_API_ROOT, 'ibapi'), 'ibapi'),
    ],
    hiddenimports=[
        'pandas',
        'pytz',
        'openpyxl',
        'python-dateutil',
        'PyQt6',
        'protobuf',
        # IB API imports
        'ibapi',
        'ibapi.client',
        'ibapi.wrapper',
        'ibapi.common',
        'ibapi.contract',
        'ibapi.order',
        'ibapi.order_state',
        'ibapi.execution',
        'ibapi.commission_report',
        'ibapi.utils',
        'ibapi.errors',
        'ibapi.decoder',
        'ibapi.connection',
        'ibapi.message',
        'ibapi.reader',
        'ibapi.comm',
        'ibapi.ticktype',
        # Project imports
        'src',
        'src.utils',
        'src.broker',
        'src.gui',
        'src.markets',
        'src.account',
        'src.trades',
        'src.ib_api',
        'src.oms',
        'src.config',
        'src.config.globals',
        'src.config.globals.addresses',
        'src.config.globals.config',
        'src.config.globals.email_manager',
        'src.config.globals.log_setup',
        'src.config.globals.signals',
        'src.config.globals.trading'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='oms',
    debug=True,  # Enable debug mode to see more error information
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Enable console to see error messages
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
