# Malha PID Temperatura - Chuveiro
# Exporta classes e funções com nomes em português para uso no projeto.

from .graficos import Plotador, plotar_erro, plotar_regime_zoom, plotar_resposta
from .modelo_chuveiro import ModeloChuveiro, ModoControlePotencia, ParamsChuveiro
from .pid_controller import ControladorPID, ParamsPID
from .potenciometro import MapeamentoPotenciometro
from .simulation import AmbienteSimulacao, ConfiguracaoSimulacao

__all__ = [
    "ModeloChuveiro",
    "ModoControlePotencia",
    "ParamsChuveiro",
    "ControladorPID",
    "ParamsPID",
    "MapeamentoPotenciometro",
    "AmbienteSimulacao",
    "ConfiguracaoSimulacao",
    "Plotador",
    "plotar_resposta",
    "plotar_erro",
    "plotar_regime_zoom",
]
