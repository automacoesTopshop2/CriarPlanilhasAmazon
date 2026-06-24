# ==============================================================================
# UTILITÁRIOS GERAIS
# ==============================================================================
# Este módulo contém funções auxiliares utilizadas em todo o sistema.
#
# Funções:
#   - Normalização de texto
#   - Tratamento de SKU
#   - Formatação de valores
#   - Manipulação de arquivos
#   - Logging e tratamento de erros
# ==============================================================================

import os
import re
import shutil
import unicodedata
import traceback
from typing import Optional, List, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LogErro:
    """
    Estrutura para armazenar informações de erro/aviso durante processamento.
    
    Attributes:
        sku: SKU relacionado ao erro
        tipo: Tipo do log ('Erro', 'Aviso', 'Info')
        mensagem: Descrição do problema
        linha: Linha onde ocorreu (opcional)
        traceback: Stack trace completo (opcional)
    """
    sku: str
    tipo: str  # 'Erro', 'Aviso', 'Info'
    mensagem: str
    linha: Optional[int] = None
    traceback: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


class Utilitarios:
    """
    Classe com métodos utilitários estáticos para processamento de dados.
    
    Esta classe contém funções auxiliares que são utilizadas em
    diferentes partes do sistema, como normalização de texto,
    formatação de valores e manipulação de arquivos.
    """
    
    # -------------------------------------------------------------------------
    # NORMALIZAÇÃO DE TEXTO
    # -------------------------------------------------------------------------
    
    @staticmethod
    def normalizar_texto(texto: Any) -> str:
        """
        Padroniza texto para comparação (minúsculas, sem acentos, sem espaços extras).
        
        Esta função é fundamental para o mapeamento de colunas, pois permite
        comparar nomes de colunas independente de acentuação ou capitalização.
        
        Args:
            texto: Texto a ser normalizado (pode ser qualquer tipo)
            
        Returns:
            Texto normalizado em minúsculas, sem acentos
            
        Examples:
            >>> Utilitarios.normalizar_texto("Descrição do Produto")
            'descricao do produto'
            >>> Utilitarios.normalizar_texto("  SKU   SELLER  ")
            'sku seller'
        """
        if not texto:
            return ""
        
        # Converte para string e remove espaços extras
        texto_str = str(texto).strip().lower()
        
        # Remove acentos usando normalização Unicode
        texto_str = unicodedata.normalize('NFKD', texto_str)
        texto_str = ''.join(c for c in texto_str if not unicodedata.combining(c))
        
        # Normaliza espaços múltiplos
        texto_str = re.sub(r"\s+", ' ', texto_str)
        
        return texto_str
    
    # -------------------------------------------------------------------------
    # TRATAMENTO DE SKU
    # -------------------------------------------------------------------------
    
    @staticmethod
    def tratar_sku(sku: Any, prefixos_para_remover: Optional[List[str]] = None) -> Optional[str]:
        """
        Remove prefixos e sufixos de variação do SKU para obter a chave base.
        
        O SKU pode conter prefixos de conta (ex: NOGO-, ATIV-) e sufixos
        de variação (ex: -V1, -V2). Esta função remove ambos para obter
        a chave de busca nas bases de dados.
        
        Args:
            sku: SKU original completo
            prefixos_para_remover: Lista de prefixos a remover (opcional)
            
        Returns:
            SKU tratado sem prefixos/sufixos, ou None se vazio
            
        Examples:
            >>> Utilitarios.tratar_sku("NOGO-ABC123-V1", ["NOGO-", "ATIV-"])
            'ABC123'
            >>> Utilitarios.tratar_sku("K2-PRODUTO")
            'K2-PRODUTO'
        """
        if not sku:
            return None
        
        # Converte para string e padroniza
        sku_tratado = str(sku).strip().upper()

        # Remove o prefixo de conta — apenas UM, o MAIS LONGO que casa no início.
        # Usar startswith (ancorado) + ordem por tamanho decrescente evita o bug
        # de prefixos sobrepostos: ex. "NOGO-CLA-9652" deve casar "NOGO-CLA-"
        # (e virar "9652"), NÃO o prefixo normal "NOGO-" (que deixaria "CLA-9652").
        if prefixos_para_remover:
            for prefixo in sorted(
                (p for p in prefixos_para_remover if p), key=len, reverse=True
            ):
                prefixo_upper = prefixo.upper()
                if sku_tratado.startswith(prefixo_upper):
                    sku_tratado = sku_tratado[len(prefixo_upper):]
                    break

        # Remove sufixo de variação (-V1, -V2, etc.)
        if "-V" in sku_tratado:
            sku_tratado = sku_tratado.split("-V")[0]
        
        return sku_tratado.strip()
    
    # -------------------------------------------------------------------------
    # FORMATAÇÃO DE VALORES
    # -------------------------------------------------------------------------
    
    @staticmethod
    def formatar_decimal(valor: Any, casas_decimais: int = 2) -> str:
        """
        Formata um valor numérico como decimal com separador ponto.
        
        Converte valores com vírgula para ponto e formata com o número
        especificado de casas decimais.
        
        Args:
            valor: Valor a ser formatado (pode ser string ou número)
            casas_decimais: Quantidade de casas decimais (padrão: 2)
            
        Returns:
            String formatada com separador decimal ponto
            
        Examples:
            >>> Utilitarios.formatar_decimal("1,5")
            '1.50'
            >>> Utilitarios.formatar_decimal(10)
            '10.00'
            >>> Utilitarios.formatar_decimal(None)
            '0.00'
        """
        if valor is None:
            return f"0.{('0' * casas_decimais)}"
        
        try:
            # Substitui vírgula por ponto
            valor_str = str(valor).replace(',', '.')
            valor_float = float(valor_str)
            return f"{valor_float:.{casas_decimais}f}"
        except (ValueError, TypeError):
            return f"0.{('0' * casas_decimais)}"
    
    @staticmethod
    def valor_para_float(valor: Any, padrao: float = 0.0) -> float:
        """
        Converte um valor para float de forma segura.
        
        Args:
            valor: Valor a ser convertido
            padrao: Valor retornado em caso de falha
            
        Returns:
            Valor como float ou o valor padrão
        """
        if valor is None:
            return padrao
        
        try:
            valor_str = str(valor).replace(',', '.')
            return float(valor_str)
        except (ValueError, TypeError):
            return padrao
    
    # -------------------------------------------------------------------------
    # MANIPULAÇÃO DE ARQUIVOS
    # -------------------------------------------------------------------------
    
    @staticmethod
    def encontrar_arquivo_onedrive(lista_caminhos: List[str], 
                                    usuario_home: Optional[str] = None) -> Optional[str]:
        """
        Procura um arquivo em múltiplos caminhos possíveis do OneDrive.
        
        Args:
            lista_caminhos: Lista de caminhos relativos/absolutos para busca
            usuario_home: Diretório home do usuário (opcional)
            
        Returns:
            Caminho completo do arquivo encontrado, ou None
        """
        if usuario_home is None:
            usuario_home = os.path.expanduser("~")
        
        for caminho in lista_caminhos:
            # Tenta caminho direto
            if os.path.exists(caminho):
                return caminho
            
            # Tenta caminho relativo ao home
            caminho_completo = os.path.join(usuario_home, caminho)
            if os.path.exists(caminho_completo):
                return caminho_completo
        
        return None
    
    @staticmethod
    def sincronizar_arquivo(lista_origens: List[str], 
                           nome_destino_local: str,
                           nome_amigavel: str,
                           usuario_home: Optional[str] = None) -> Tuple[bool, str]:
        """
        Sincroniza arquivo do OneDrive para o diretório local.
        
        Copia o arquivo apenas se a versão no OneDrive for mais recente
        que a versão local.
        
        Args:
            lista_origens: Lista de possíveis caminhos de origem
            nome_destino_local: Nome do arquivo de destino local
            nome_amigavel: Nome amigável para exibição em mensagens
            usuario_home: Diretório home do usuário
            
        Returns:
            Tupla (sucesso: bool, mensagem: str)
        """
        origem = Utilitarios.encontrar_arquivo_onedrive(lista_origens, usuario_home)
        
        if not origem:
            return False, f"❌ {nome_amigavel} não encontrado no PC."
        
        try:
            # Verifica se precisa atualizar
            precisar_atualizar = (
                not os.path.exists(nome_destino_local) or
                os.path.getmtime(origem) > os.path.getmtime(nome_destino_local)
            )
            
            if precisar_atualizar:
                shutil.copy2(origem, nome_destino_local)
                return True, f"✅ {nome_amigavel} atualizado!"
            
            return True, f"✓ {nome_amigavel} já está atualizado."
            
        except PermissionError:
            return False, f"⚠️ Sem permissão para copiar {nome_amigavel}. Feche o arquivo e tente novamente."
        except Exception as e:
            return False, f"⚠️ Erro ao copiar {nome_amigavel}: {str(e)}"
    
    @staticmethod
    def garantir_arquivos_txt(arquivo_remover: str, arquivo_substituir: str) -> None:
        """
        Garante que os arquivos de termos existam (cria vazios se necessário).
        
        Args:
            arquivo_remover: Caminho do arquivo de termos a remover
            arquivo_substituir: Caminho do arquivo de termos a substituir
        """
        for arquivo in [arquivo_remover, arquivo_substituir]:
            if not os.path.exists(arquivo):
                try:
                    with open(arquivo, 'w', encoding='utf-8') as f:
                        pass  # Cria arquivo vazio
                except Exception:
                    pass  # Ignora erros silenciosamente
    
    # -------------------------------------------------------------------------
    # TRATAMENTO DE ERROS
    # -------------------------------------------------------------------------
    
    @staticmethod
    def criar_log_erro(sku: str, tipo: str, mensagem: str, 
                       linha: Optional[int] = None,
                       incluir_traceback: bool = False) -> LogErro:
        """
        Cria um objeto de log de erro com todas as informações relevantes.
        
        Args:
            sku: SKU relacionado ao erro
            tipo: Tipo do log ('Erro', 'Aviso', 'Info')
            mensagem: Descrição do problema
            linha: Número da linha (opcional)
            incluir_traceback: Se deve incluir stack trace
            
        Returns:
            Objeto LogErro preenchido
        """
        trace = None
        if incluir_traceback:
            trace = traceback.format_exc()
        
        return LogErro(
            sku=sku,
            tipo=tipo,
            mensagem=mensagem,
            linha=linha,
            traceback=trace
        )
    
    @staticmethod
    def formatar_traceback_resumido(excecao: Exception, max_linhas: int = 5) -> str:
        """
        Formata o traceback de uma exceção de forma resumida.
        
        Args:
            excecao: Exceção capturada
            max_linhas: Número máximo de linhas do traceback
            
        Returns:
            String formatada com o traceback resumido
        """
        try:
            tb_completo = traceback.format_exception(
                type(excecao), excecao, excecao.__traceback__
            )
            linhas = []
            for linha in tb_completo:
                linhas.extend(linha.strip().split('\n'))
            
            # Retorna apenas as últimas linhas relevantes
            return '\n'.join(linhas[-max_linhas:])
        except Exception:
            return str(excecao)
    
    # -------------------------------------------------------------------------
    # VALIDAÇÕES
    # -------------------------------------------------------------------------
    
    @staticmethod
    def validar_ean(ean: Any) -> Tuple[bool, str]:
        """
        Valida um código EAN (8 ou 13 dígitos).
        
        Args:
            ean: Código EAN a validar
            
        Returns:
            Tupla (valido: bool, mensagem: str)
        """
        if not ean:
            return False, "EAN vazio"
        
        ean_str = str(ean).strip()
        
        # Remove caracteres não numéricos
        ean_limpo = re.sub(r'\D', '', ean_str)
        
        if len(ean_limpo) not in [8, 13]:
            return False, f"EAN deve ter 8 ou 13 dígitos (encontrado: {len(ean_limpo)})"
        
        return True, "EAN válido"
    
    @staticmethod
    def validar_titulo(titulo: Any, max_caracteres: int = 200) -> Tuple[bool, str]:
        """
        Valida o título do produto.
        
        Args:
            titulo: Título a validar
            max_caracteres: Limite máximo de caracteres
            
        Returns:
            Tupla (valido: bool, mensagem: str)
        """
        if not titulo:
            return False, "Título vazio"
        
        titulo_str = str(titulo).strip()
        
        if len(titulo_str) > max_caracteres:
            return False, f"Título excede {max_caracteres} caracteres ({len(titulo_str)})"
        
        return True, "Título válido"
