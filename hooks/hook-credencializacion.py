# Hook personalizado para credencializacion
# Asegura que todos los submódulos sean incluidos
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules("credencializacion")
datas = collect_data_files("credencializacion")
