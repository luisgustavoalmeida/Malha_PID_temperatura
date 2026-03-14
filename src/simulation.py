"""
Ambiente de simulação da malha fechada: chuveiro + PID + mapeamento para potenciômetro 50 kΩ.

O PID atua em potência normalizada (0–1). A simulação converte:
- para potência [W] ao alimentar o modelo do chuveiro;
- para resistência [Ω] (e DAC) para o potenciômetro comandado pelo ESP32.
"""

from dataclasses import dataclass
from typing import List, Optional, Callable
import numpy as np

from .shower_model import ModeloChuveiro, ParamsChuveiro
from .pid_controller import ControladorPID, ParamsPID
from .potentiometer import MapeamentoPotenciometro
from .curva_vazao_fabricante import vazao_por_pressao


@dataclass
class ConfiguracaoSimulacao:
    """
    Configuração de uma corrida de simulação: duração, passo, vazão (ou pressão) e setpoint.

    A vazão pode ser definida de duas formas:
    - vazao_lmin: valor fixo [L/min] durante toda a simulação.
    - pressao_entrada_mca: se definido, a vazão é obtida da curva do fabricante
      (Vazão × Pressão de Entrada) e vazao_lmin é ignorado.
    """

    duracao_s: float = 120.0       # Duração total da simulação [s]
    dt_s: float = 0.1              # Passo de integração [s]
    vazao_lmin: float = 2.5       # Vazão fixa [L/min]; usado só se pressao_entrada_mca for None
    pressao_entrada_mca: Optional[float] = None  # Pressão da rede [m.c.a.]; se definido, vazão = curva do fabricante
    # Setpoint: constante ou função do tempo setpoint(t) -> °C
    setpoint_constante: Optional[float] = None
    setpoint_funcao: Optional[Callable[[float], float]] = None


class AmbienteSimulacao:
    """
    Ambiente de simulação da malha fechada:
    setpoint -> PID -> potência -> chuveiro -> temperatura na saída.
    Armazena histórico de tempo, setpoint, temperatura, potência e resistência.
    """

    def __init__(
        self,
        params_chuveiro: Optional[ParamsChuveiro] = None,
        params_pid: Optional[ParamsPID] = None,
        mapeamento_potenciometro: Optional[MapeamentoPotenciometro] = None,
    ):
        self.chuveiro = ModeloChuveiro(params_chuveiro)
        self.controlador_pid = ControladorPID(
            params_pid or ParamsPID(saida_minima=0.0, saida_maxima=1.0)
        )
        self.potenciometro = mapeamento_potenciometro or MapeamentoPotenciometro()
        self.params_chuveiro = self.chuveiro.params
        self.params_pid = self.controlador_pid.params

        # Históricos da última simulação (preenchidos por executar())
        self.tempo_hist: List[float] = []
        self.setpoint_hist: List[float] = []
        self.temperatura_hist: List[float] = []
        self.potencia_norm_hist: List[float] = []
        self.potencia_w_hist: List[float] = []
        self.resistencia_hist: List[float] = []
        self.erro_hist: List[float] = []

    def _obter_setpoint(self, tempo: float, config: ConfiguracaoSimulacao) -> float:
        """Retorna o setpoint no instante dado (função ou constante)."""
        if config.setpoint_funcao is not None:
            return config.setpoint_funcao(tempo)
        if config.setpoint_constante is not None:
            return config.setpoint_constante
        return self.params_chuveiro.temperatura_desejada

    def executar(self, config: Optional[ConfiguracaoSimulacao] = None) -> None:
        """
        Executa uma simulação e armazena resultados nos históricos:
        tempo, setpoint, temperatura, potência normalizada, potência [W], resistência, erro.
        """
        cfg = config or ConfiguracaoSimulacao()
        self.chuveiro.reiniciar()
        self.controlador_pid.reiniciar()
        self.chuveiro.definir_passo_tempo(cfg.dt_s)

        pot_min = self.params_chuveiro.potencia_minima
        pot_max = self.params_chuveiro.potencia_maxima
        # Vazão: da curva do fabricante (pressão) ou valor fixo
        if cfg.pressao_entrada_mca is not None:
            vazao = vazao_por_pressao(cfg.pressao_entrada_mca)
        else:
            vazao = cfg.vazao_lmin

        numero_passos = int(cfg.duracao_s / cfg.dt_s) + 1
        self.tempo_hist = [i * cfg.dt_s for i in range(numero_passos)]
        self.setpoint_hist = []
        self.temperatura_hist = []
        self.potencia_norm_hist = []
        self.potencia_w_hist = []
        self.resistencia_hist = []
        self.erro_hist = []

        for i, tempo_atual in enumerate(self.tempo_hist):
            setpoint = self._obter_setpoint(tempo_atual, cfg)
            temperatura_medida = self.chuveiro.temperatura_saida

            # PID: saída normalizada 0–1
            acao_norm = self.controlador_pid.passo(
                setpoint, temperatura_medida, tempo_atual
            )
            # Potência em W para o modelo do chuveiro
            potencia_w = pot_min + acao_norm * (pot_max - pot_min)
            # Resistência do potenciômetro para o ESP32
            resistencia_ohm = self.potenciometro.potencia_para_resistencia_ohms(
                acao_norm
            )

            temperatura_saida = self.chuveiro.passo(potencia_w, vazao)

            self.setpoint_hist.append(setpoint)
            self.temperatura_hist.append(temperatura_saida)
            self.potencia_norm_hist.append(acao_norm)
            self.potencia_w_hist.append(potencia_w)
            self.resistencia_hist.append(resistencia_ohm)
            self.erro_hist.append(setpoint - temperatura_saida)

    def obter_resultados(self) -> dict:
        """Retorna dicionário com arrays numpy (tempo, setpoint, temperatura, etc.) para plot e análise."""
        return {
            "tempo": np.array(self.tempo_hist),
            "setpoint": np.array(self.setpoint_hist),
            "temperatura": np.array(self.temperatura_hist),
            "potencia_norm": np.array(self.potencia_norm_hist),
            "potencia_w": np.array(self.potencia_w_hist),
            "resistencia_ohm": np.array(self.resistencia_hist),
            "erro": np.array(self.erro_hist),
        }
