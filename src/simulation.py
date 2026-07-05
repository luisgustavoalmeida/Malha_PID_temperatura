"""
Ambiente de simulação da malha fechada: chuveiro + PID + mapeamento para potenciômetro 50 kΩ.

O PID atua em potência normalizada (0–1). A simulação converte:
- para potência [W] ao alimentar o modelo do chuveiro;
- para resistência [Ω] (e DAC) para o potenciômetro comandado pelo ESP32.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

from .modelo_chuveiro import ModeloChuveiro, ParamsChuveiro
from .pid_controller import ControladorPID, ParamsPID
from .potenciometro import MapeamentoPotenciometro


def processar_leitura_sensor(
    temperatura_bruta: float,
    buffer_amostras: List[float],
    resolucao_c: Optional[float],
    janela_media_movel: int,
) -> float:
    """
    Modela a cadeia de leitura do sensor (como no ESP32):
    1. Quantização: round(temp / resolucao) * resolucao
    2. Média móvel das últimas amostras quantizadas
    """
    amostra = temperatura_bruta
    if resolucao_c is not None and resolucao_c > 0:
        amostra = round(amostra / resolucao_c) * resolucao_c

    buffer_amostras.append(amostra)
    janela = max(1, janela_media_movel)
    while len(buffer_amostras) > janela:
        buffer_amostras.pop(0)

    if janela <= 1:
        return float(amostra)
    return float(np.mean(buffer_amostras))


@dataclass
class ConfiguracaoSimulacao:
    """
    Configuração de uma corrida de simulação da malha fechada.

    Define duração, passo da planta, vazão, setpoint, tempos de sensor/PID,
    modelo do sensor (quantização e filtro) e perturbações opcionais.
    """

    # Duração total da simulação [s]
    duracao_s: float = 120.0
    # Passo de integração da planta (modelo físico) [s]. Menor = mais preciso, mais lento
    dt_s: float = 0.1
    # Vazão de água fixa durante toda a simulação [L/min]
    vazao_lmin: float = 2.0
    # Período entre leituras do sensor [s]. None ou 0 = a cada dt_s (contínuo)
    tempo_aquisicao_sensor_s: Optional[float] = None
    # Período entre atualizações do PID [s]. None ou 0 = a cada dt_s (contínuo)
    tempo_calculo_pid_s: Optional[float] = None
    # Passo de quantização da leitura [°C]: round(temp/resolucao)*resolucao (ESP32: 0.125)
    sensor_resolucao_c: Optional[float] = 0.125
    # Janela da média móvel sobre amostras quantizadas; 1 = sem filtro
    sensor_janela_media_movel: int = 3
    # Setpoint constante [°C]; ignorado se setpoint_funcao estiver definida
    setpoint_constante: Optional[float] = None
    # Lei do setpoint: função tempo [s] → temperatura [°C] (ex.: degrau, rampa)
    setpoint_funcao: Optional[Callable[[float], float]] = None
    # Bias adicional na medição do sensor [°C]: função tempo → desvio
    perturbacao_medicao: Optional[Callable[[float], float]] = None
    # Perturbação na temperatura da água de entrada [°C]: função tempo → desvio
    perturbacao_entrada: Optional[Callable[[float], float]] = None
    # Atraso para aplicar mudança de setpoint na malha [s] (ESP32: ALVO_TEMP_PAUSA_MS = 1,5)
    # None ou 0 = setpoint da função aplicado imediatamente (degrau clássico)
    setpoint_atraso_aplicacao_s: Optional[float] = 1.5


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
        """
        Monta a malha fechada chuveiro + PID + potenciômetro.

        Usa um único ControladorPID (como no firmware ESP32, sem troca partida/regime).

        params_chuveiro: modelo físico da planta.
        params_pid: ganhos e limites do PID.
        mapeamento_potenciometro: conversão saída normalizada → resistência [Ω].
        """
        self.chuveiro = ModeloChuveiro(params_chuveiro)
        params_base = params_pid or ParamsPID(saida_minima=0.0, saida_maxima=1.0)
        self.controlador_pid = ControladorPID(params_base)
        self.potenciometro = mapeamento_potenciometro or MapeamentoPotenciometro()
        self.params_chuveiro = self.chuveiro.params
        self.params_pid = params_base

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

        periodo_sensor = (
            cfg.tempo_aquisicao_sensor_s
            if cfg.tempo_aquisicao_sensor_s and cfg.tempo_aquisicao_sensor_s > 0
            else cfg.dt_s
        )
        periodo_pid = (
            cfg.tempo_calculo_pid_s
            if cfg.tempo_calculo_pid_s and cfg.tempo_calculo_pid_s > 0
            else cfg.dt_s
        )

        numero_passos = int(cfg.duracao_s / cfg.dt_s) + 1
        self.tempo_hist = [i * cfg.dt_s for i in range(numero_passos)]
        self.setpoint_hist = []
        self.temperatura_hist = []
        self.potencia_norm_hist = []
        self.potencia_w_hist = []
        self.resistencia_hist = []
        self.erro_hist = []

        temperatura_medida = self.chuveiro.temperatura_saida
        acao_norm = 0.0
        proxima_aquisicao_sensor = 0.0
        proximo_calculo_pid = 0.0
        buffer_sensor: List[float] = []

        setpoint_alvo = self._obter_setpoint(0.0, cfg)
        setpoint_malha = setpoint_alvo
        setpoint_alvo_anterior = setpoint_alvo
        tempo_mudanca_setpoint = 0.0
        atraso_sp = cfg.setpoint_atraso_aplicacao_s or 0.0

        for tempo_atual in self.tempo_hist:
            setpoint_alvo = self._obter_setpoint(tempo_atual, cfg)

            if abs(setpoint_alvo - setpoint_alvo_anterior) > 1e-6:
                tempo_mudanca_setpoint = tempo_atual
                setpoint_alvo_anterior = setpoint_alvo
                if atraso_sp <= 0 and abs(setpoint_malha - setpoint_alvo) > 1e-6:
                    setpoint_malha = setpoint_alvo
                    self.controlador_pid.sincronizar_integral_para_saida(
                        acao_norm, setpoint_malha, temperatura_medida
                    )

            if (
                atraso_sp > 0
                and abs(setpoint_malha - setpoint_alvo) > 1e-6
                and tempo_atual - tempo_mudanca_setpoint >= atraso_sp
            ):
                setpoint_malha = setpoint_alvo
                self.controlador_pid.sincronizar_integral_para_saida(
                    acao_norm, setpoint_malha, temperatura_medida
                )

            setpoint = setpoint_malha
            delta_entrada = self._perturbacao(cfg.perturbacao_entrada, tempo_atual)
            temperatura_entrada = temp_entrada_base + delta_entrada

            if tempo_atual >= proxima_aquisicao_sensor:
                temperatura_planta = self.chuveiro.temperatura_saida
                bias_medicao = self._perturbacao(cfg.perturbacao_medicao, tempo_atual)
                temperatura_bruta = temperatura_planta + bias_medicao
                temperatura_medida = processar_leitura_sensor(
                    temperatura_bruta,
                    buffer_sensor,
                    cfg.sensor_resolucao_c,
                    cfg.sensor_janela_media_movel,
                )
                proxima_aquisicao_sensor += periodo_sensor

            if tempo_atual >= proximo_calculo_pid:
                acao_norm = self.controlador_pid.passo(
                    setpoint, temperatura_medida, tempo_atual
                )
                proximo_calculo_pid += periodo_pid

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

            self.setpoint_hist.append(setpoint)
            self.temperatura_hist.append(temperatura_saida)
            self.potencia_norm_hist.append(acao_norm_aplicada)
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
