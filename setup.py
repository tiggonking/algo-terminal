from cx_Freeze import setup, Executable

setup(
    name="AlgoTerminal",
    version="1.1",
    description="the best terminal for trading",
    executables=[Executable("/algoterminal/src/oms/oms.py")]
)