from cx_Freeze import setup, Executable

# Change the path to the path of the oms.py file on your system for a build.
setup(
    name="AlgoTerminal",
    version="1.1",
    description="the best terminal for trading",
    executables=[Executable("C:/Users/DELL/Documents/Code/Algo_Terminal/src/oms/oms.py")]
)