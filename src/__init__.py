# Malha PID Temperatura - Chuveiro
# Exporta classes e funções com nomes em português para uso no projeto.

from .shower_model import ModeloChuveiro, ParamsChuveiro
from .pid_controller import ControladorPID, ParamsPID
from .potentiometer import MapeamentoPotenciometro
from .simulation import AmbienteSimulacao, ConfiguracaoSimulacao
from .plotter import Plotador, plotar_resposta, plotar_erro

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
