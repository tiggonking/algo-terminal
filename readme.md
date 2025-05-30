# Build python package

From within devcontainer run:

```bash
uv build
```

# Build exe
You will need pyinstaller installed in your environment.

First, pip install the package
```bash
pip install -e .
```
in git terminal run the fulling to create the exe build:

```bash
pyinstaller --onefile --windowed src/oms/oms.py 
```