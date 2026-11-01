# Empacotamento

O build oficial fica nos scripts da raiz:

- `python3 build.py` gera o executável único com PyInstaller (`dist/ps2coop` ou `dist/ps2coop.exe`).
- `python3 tools/package.py` gera os pacotes de distribuição (`dist/PS2Coop-Windows.zip` e `dist/PS2Coop-Linux.tar.gz`).
- `tools/bootstrap-python.ps1` é usado pelo `iniciar.bat` quando o Windows não tem Python.

O workflow `.github/workflows/build.yml` roda testes, compila e empacota em Linux e Windows.
