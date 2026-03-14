"""
Ambiente de resposta ao degrau: setpoint constante até um instante, depois sobe para a temperatura desejada.

Útil para aferir tempo de subida, overshoot e tempo de estabilização da malha PID.
"""

from typing import Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import ParamsChuveiro, ParamsPID, ConfiguracaoSimulacao
from .ambiente_base import AmbienteBase


class AmbienteRespostaDegrau(AmbienteBase):
    """
    Setpoint permanece em um valor inicial até o instante t_degrau_s;
    a partir daí passa para a temperatura_desejada dos parâmetros do chuveiro.
    """

    def __init__(
        self,
        t_degrau_s: float = 10.0,
        setpoint_inicial: Optional[float] = None,
        params_chuveiro: Optional[ParamsChuveiro] = None,
        params_pid: Optional[ParamsPID] = None,
        duracao_s: float = 120.0,
        dt_s: float = 0.1,
        vazao_lmin: float = 2.5,
    ):
        """
        Inicializa o ambiente de resposta ao degrau.

        Argumentos:
            t_degrau_s: instante [s] em que o setpoint muda para temperatura_desejada.
            setpoint_inicial: valor do setpoint antes do degrau; None = temperatura_inicial_agua.
            params_chuveiro: parâmetros do chuveiro; None = padrão.
            params_pid: parâmetros do PID; None = padrão.
            duracao_s: duração da simulação [s].
            dt_s: passo de integração [s].
            vazao_lmin: vazão fixa [L/min].
        """
        super().__init__(
            params_chuveiro=params_chuveiro,
            params_pid=params_pid,
        )
        self.t_degrau_s = t_degrau_s
        self.setpoint_inicial = setpoint_inicial
        self.duracao_s = duracao_s
        self.dt_s = dt_s
        self.vazao_lmin = vazao_lmin

    def obter_configuracao(self) -> ConfiguracaoSimulacao:
        """Configuração com setpoint em degrau no instante t_degrau_s."""
        temp_inicial = (
            self.setpoint_inicial
            if self.setpoint_inicial is not None
            else self.params_chuveiro.temperatura_inicial_agua
        )
        temp_desejada = self.params_chuveiro.temperatura_desejada

        def setpoint_funcao(tempo: float) -> float:
            return temp_desejada if tempo >= self.t_degrau_s else temp_inicial

        return ConfiguracaoSimulacao(
            duracao_s=self.duracao_s,
            dt_s=self.dt_s,
            vazao_lmin=self.vazao_lmin,
            setpoint_funcao=setpoint_funcao,
        )
