"""
Ambiente de simulação da malha fechada: chuveiro + PID + mapeamento para potenciômetro 50 kΩ.

O PID atua em potência normalizada (0–1). A simulação converte:
- para potência [W] ao alimentar o modelo do chuveiro;
- para resistência [Ω] (e DAC) para o potenciômetro comandado pelo ESP32.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Union

import numpy as np

from .modelo_chuveiro import ModeloChuveiro, ParamsChuveiro
from .pid_controller import (
    ControladorPID,
    ControladorPIDComAgendamento,
    ControladorPIDDual,
    CriterioTrocaRegime,
    ParamsPID,
)
from .potenciometro import MapeamentoPotenciometro

ControladorMalha = Union[ControladorPID, ControladorPIDComAgendamento, ControladorPIDDual]


@dataclass
class ConfiguracaoSimulacao:
    """
    Configuração de uma corrida de simulação: duração, passo, vazão e setpoint.

    A vazão é informada diretamente em vazao_lmin [L/min] durante toda a simulação.
    """

    duracao_s: float = 120.0       # Duração total da simulação [s]
    dt_s: float = 0.1              # Passo de integração [s]
    vazao_lmin: float = 2.5        # Vazão fixa [L/min]
    # Setpoint: constante ou função do tempo setpoint(t) -> °C
    setpoint_constante: Optional[float] = None
    setpoint_funcao: Optional[Callable[[float], float]] = None
    # Perturbações opcionais (°C): bias na medição do sensor ou na água de entrada
    perturbacao_medicao: Optional[Callable[[float], float]] = None
    perturbacao_entrada: Optional[Callable[[float], float]] = None


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
        params_pid_regime: Optional[ParamsPID] = None,
        limiar_erro_partida: float = 2.0,
        limiar_erro_regime: float = 0.8,
        t_troca_regime_s: Optional[float] = None,
        criterio_troca_regime: CriterioTrocaRegime = "tempo",
        usar_pid_dual_legacy: bool = False,
        mapeamento_potenciometro: Optional[MapeamentoPotenciometro] = None,
    ):
        self.chuveiro = ModeloChuveiro(params_chuveiro)
        params_base = params_pid or ParamsPID(saida_minima=0.0, saida_maxima=1.0)
        if params_pid_regime is not None:
            if usar_pid_dual_legacy:
                self.controlador_pid: ControladorMalha = ControladorPIDDual(
                    params_partida=params_base,
                    params_regime=params_pid_regime,
                    limiar_partida=limiar_erro_partida,
                    limiar_regime=limiar_erro_regime,
                    t_troca_regime_s=t_troca_regime_s,
                    criterio_troca=criterio_troca_regime,
                )
            else:
                self.controlador_pid = ControladorPIDComAgendamento(
                    params_partida=params_base,
                    params_regime=params_pid_regime,
                    t_troca_regime_s=t_troca_regime_s,
                    criterio_troca=criterio_troca_regime,
                    limiar_partida=limiar_erro_partida,
                    limiar_regime=limiar_erro_regime,
                )
            self._pid_agendado = True
        else:
            self.controlador_pid = ControladorPID(params_base)
            self._pid_agendado = False
        self.potenciometro = mapeamento_potenciometro or MapeamentoPotenciometro()
        self.params_chuveiro = self.chuveiro.params
        self.params_pid = params_base
        self.params_pid_regime = params_pid_regime

        # Históricos da última simulação (preenchidos por executar())
        self.tempo_hist: List[float] = []
        self.setpoint_hist: List[float] = []
        self.temperatura_hist: List[float] = []
        self.potencia_norm_hist: List[float] = []
        self.potencia_w_hist: List[float] = []
        self.resistencia_hist: List[float] = []
        self.erro_hist: List[float] = []
        self.modo_pid_hist: List[str] = []
        self._dual_pid = self._pid_agendado

    def _obter_setpoint(self, tempo: float, config: ConfiguracaoSimulacao) -> float:
        """Retorna o setpoint no instante dado (função ou constante)."""
        if config.setpoint_funcao is not None:
            return config.setpoint_funcao(tempo)
        if config.setpoint_constante is not None:
            return config.setpoint_constante
        return self.params_chuveiro.temperatura_desejada

    def _perturbacao(self, funcao: Optional[Callable[[float], float]], tempo: float) -> float:
        if funcao is None:
            return 0.0
        return float(funcao(tempo))

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
        vazao = cfg.vazao_lmin
        temp_entrada_base = self.params_chuveiro.temperatura_inicial_agua

        numero_passos = int(cfg.duracao_s / cfg.dt_s) + 1
        self.tempo_hist = [i * cfg.dt_s for i in range(numero_passos)]
        self.setpoint_hist = []
        self.temperatura_hist = []
        self.potencia_norm_hist = []
        self.potencia_w_hist = []
        self.resistencia_hist = []
        self.erro_hist = []
        self.modo_pid_hist = []

        for tempo_atual in self.tempo_hist:
            setpoint = self._obter_setpoint(tempo_atual, cfg)
            temperatura_planta = self.chuveiro.temperatura_saida
            bias_medicao = self._perturbacao(cfg.perturbacao_medicao, tempo_atual)
            temperatura_medida = temperatura_planta + bias_medicao
            delta_entrada = self._perturbacao(cfg.perturbacao_entrada, tempo_atual)
            temperatura_entrada = temp_entrada_base + delta_entrada

            acao_norm = self.controlador_pid.passo(
                setpoint, temperatura_medida, tempo_atual
            )
            potencia_solicitada_w = pot_min + acao_norm * (pot_max - pot_min)
            temperatura_saida = self.chuveiro.passo(
                potencia_solicitada_w, vazao, temperatura_entrada=temperatura_entrada
            )

            potencia_w = self.chuveiro.ultima_potencia_aplicada_w
            faixa_pot = pot_max - pot_min
            acao_norm_aplicada = (
                (potencia_w - pot_min) / faixa_pot if faixa_pot > 0 else 0.0
            )
            resistencia_ohm = self.potenciometro.potencia_para_resistencia_ohms(
                acao_norm_aplicada
            )

            modo = (
                self.controlador_pid.modo_atual
                if self._pid_agendado
                else "unico"
            )

            self.setpoint_hist.append(setpoint)
            self.temperatura_hist.append(temperatura_saida)
            self.potencia_norm_hist.append(acao_norm_aplicada)
            self.potencia_w_hist.append(potencia_w)
            self.resistencia_hist.append(resistencia_ohm)
            self.erro_hist.append(setpoint - temperatura_saida)
            self.modo_pid_hist.append(modo)

    def obter_resultados(self) -> dict:
        """Retorna dicionário com arrays numpy (tempo, setpoint, temperatura, etc.) para plot e análise."""
        resultados = {
            "tempo": np.array(self.tempo_hist),
            "setpoint": np.array(self.setpoint_hist),
            "temperatura": np.array(self.temperatura_hist),
            "potencia_norm": np.array(self.potencia_norm_hist),
            "potencia_w": np.array(self.potencia_w_hist),
            "resistencia_ohm": np.array(self.resistencia_hist),
            "erro": np.array(self.erro_hist),
        }
        if self._pid_agendado:
            resultados["modo_pid"] = np.array(self.modo_pid_hist)
        return resultados
