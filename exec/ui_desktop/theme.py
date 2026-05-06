# ==============================================================================
# THEME - Paleta e fontes da UI desktop (modo dark "very black")
# ==============================================================================

class Cores:
    # --- Backgrounds ---
    APP_BG = "#050505"          # fundo geral (quase preto)
    SIDEBAR_BG = "#000000"      # sidebar pura preta
    CARD_BG = "#0e0e0e"         # cartões / frames
    INPUT_BG = "#161616"        # entradas / textboxes
    HOVER_BG = "#1a1a1a"        # hover sutil

    # --- Bordas ---
    BORDER = "#1f1f1f"
    BORDER_FORTE = "#2a2a2a"

    # --- Texto ---
    TEXT_PRIMARY = "#f5f5f5"
    TEXT_MUTED = "#7a7a7a"
    SIDEBAR_FG = "#e5e5e5"
    SIDEBAR_FG_MUTED = "#6b7280"
    SIDEBAR_ACTIVE = "#0f0f0f"
    SIDEBAR_HIGHLIGHT = "#1e3a8a"   # azul escuro destacado

    # --- Acentos / Ações ---
    PRIMARY = "#2563eb"
    PRIMARY_HOVER = "#1d4ed8"
    SUCCESS = "#16a34a"
    SUCCESS_HOVER = "#15803d"
    DANGER = "#dc2626"
    DANGER_HOVER = "#b91c1c"
    WARNING = "#d97706"
    INFO = "#0891b2"

    # --- Compatibilidade (chaves antigas) ---
    MUTED = TEXT_MUTED
    BORDER_LIGHT = BORDER
    BORDER_DARK = BORDER_FORTE
    CARD_BG_LIGHT = CARD_BG
    CARD_BG_DARK = CARD_BG


class Fontes:
    TITULO = ("Segoe UI", 22, "bold")
    SUBTITULO = ("Segoe UI", 16, "bold")
    SECAO = ("Segoe UI", 13, "bold")
    CORPO = ("Segoe UI", 12)
    PEQUENA = ("Segoe UI", 11)
    BOTAO = ("Segoe UI", 12, "bold")
    MONOESPACO = ("Consolas", 10)
