from setuptools import setup, find_packages
from cx_Freeze import setup, Executable

# Change the path to the path of the oms.py file on your system for a build.
setup(
    name="AlgoTerminal",
    version="1.1",
    description="the best terminal for trading",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "pandas>=2.2.3",
        "pytz>=2022.7.1",
        "openpyxl>=3.1.2",
        "python-dateutil>=2.8.2",
        "PyQt6",
    ],
    executables=[Executable("src/oms/oms.py")]
)