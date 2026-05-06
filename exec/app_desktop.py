# ==============================================================================
# SISTEMA DE PLANILHAS AMAZON - APLICATIVO DESKTOP
# ==============================================================================
# Ponto de entrada do app .exe (substitui o Streamlit `app.py`).
#
# Mantém a mesma lógica dos módulos `core/` (preços, descrição, processadores)
# e troca a UI Streamlit por uma janela CustomTkinter nativa.
#
# Para empacotar como executável:
#   pyinstaller --noconsole --onefile --name "PlanilhasAmazon" ^
#               --collect-all customtkinter app_desktop.py
# ==============================================================================

import sys
import os

# Quando rodando dentro do PyInstaller (--onefile), garante que o diretório
# de trabalho aponte para a pasta do executável, e não para o _MEIPASS temp.
if getattr(sys, "frozen", False):
    try:
        os.chdir(os.path.dirname(sys.executable))
    except Exception:
        pass
else:
    # Em desenvolvimento: raiz do projeto é pai de exec/
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(_root)
    if _root not in sys.path:
        sys.path.insert(0, _root)

from ui_desktop import MainWindow


def main() -> None:
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
