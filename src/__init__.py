# Malha PID Temperatura - Chuveiro
# Exporta classes e funções com nomes em português para uso no projeto.

from .modelo_chuveiro import ModeloChuveiro, ParamsChuveiro
from .pid_controller import ControladorPID, ParamsPID
from .potenciometro import MapeamentoPotenciometro
from .simulation import AmbienteSimulacao, ConfiguracaoSimulacao
from .graficos import Plotador, plotar_resposta, plotar_erro

__all__ = [
    "ModeloChuveiro",
    "ParamsChuveiro",
    "ControladorPID",
    "ParamsPID",
    "MapeamentoPotenciometro",
    "AmbienteSimulacao",
    "ConfiguracaoSimulacao",
    "Plotador",
    "plotar_resposta",
    "plotar_erro",
]
