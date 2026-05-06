# ==============================================================================
# UI - Módulo de Interface do Usuário
# ==============================================================================
# Este pacote contém componentes de interface Streamlit reutilizáveis.
#
# Componentes:
#   - Sidebar: Barra lateral com gerenciamento de bases de dados
#   - Componentes: Elementos de UI reutilizáveis
# ==============================================================================

from .componentes import ComponentesUI
from .sidebar import SidebarUI

__all__ = ['ComponentesUI', 'SidebarUI']
