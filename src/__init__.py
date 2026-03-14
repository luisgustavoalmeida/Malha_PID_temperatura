# Malha PID Temperatura - Chuveiro
# Exporta classes e funções com nomes em português para uso no projeto.

from .shower_model import ModeloChuveiro, ParamsChuveiro
from .pid_controller import ControladorPID, ParamsPID
from .potentiometer import MapeamentoPotenciometro
from .simulation import AmbienteSimulacao, ConfiguracaoSimulacao
from .plotter import Plotador, plotar_resposta, plotar_erro
from .curva_vazao_fabricante import (
    vazao_por_pressao,
    pressao_por_vazao,
    obter_pontos_curva,
    CURVA_VAZAO_PRESSAO_FABRICANTE,
    PRESSAO_MINIMA_MCA,
    PRESSAO_MAXIMA_MCA,
    VAZAO_MINIMA_CURVA_LMIN,
    VAZAO_MAXIMA_CURVA_LMIN,
)

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
    "vazao_por_pressao",
    "pressao_por_vazao",
    "obter_pontos_curva",
    "CURVA_VAZAO_PRESSAO_FABRICANTE",
    "PRESSAO_MINIMA_MCA",
    "PRESSAO_MAXIMA_MCA",
    "VAZAO_MINIMA_CURVA_LMIN",
    "VAZAO_MAXIMA_CURVA_LMIN",
]
