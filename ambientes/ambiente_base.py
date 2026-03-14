"""
Ambiente base para testes da malha PID: define interface comum e cenários de setpoint.

Cada ambiente de teste (resposta ao degrau, sintonia por ML, etc.) herda desta classe
e implementa obter_configuracao() para definir duração, vazão e lei do setpoint.
"""

from abc import ABC, abstractmethod
from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import AmbienteSimulacao, ConfiguracaoSimulacao, ParamsChuveiro, ParamsPID
from src.graficos import Plotador


class AmbienteBase(ABC):
    """
    Interface para ambientes de teste da malha PID.
    Subclasses devem implementar obter_configuracao().
    """

    def __init__(
        self,
        params_chuveiro: Optional[ParamsChuveiro] = None,
        params_pid: Optional[ParamsPID] = None,
    ):
        self.params_chuveiro = params_chuveiro or ParamsChuveiro()
        self.params_pid = params_pid or ParamsPID(saida_minima=0.0, saida_maxima=1.0)
        self.simulacao = AmbienteSimulacao(
            params_chuveiro=self.params_chuveiro,
            params_pid=self.params_pid,
        )

    @abstractmethod
    def obter_configuracao(self) -> ConfiguracaoSimulacao:
        """Retorna a configuração da simulação (duração, setpoint, vazão, etc.)."""
        pass

    def executar(
        self, config: Optional[ConfiguracaoSimulacao] = None
    ) -> dict:
        """Executa a simulação e retorna o dicionário de resultados (arrays)."""
        cfg = config or self.obter_configuracao()
        self.simulacao.executar(cfg)
        return self.simulacao.obter_resultados()

    def executar_e_plotar(
        self,
        caminho_base: Optional[str] = None,
        titulo: Optional[str] = None,
    ):
        """
        Executa a simulação, gera os gráficos e opcionalmente salva em arquivo.
        Retorna (resultados, plotador).
        """
        resultados = self.executar()
        plotador = Plotador(resultados)
        plotador.plotar_tudo(
            caminho_base=caminho_base,
            titulo=titulo or self.__class__.__name__,
        )
        return resultados, plotador
