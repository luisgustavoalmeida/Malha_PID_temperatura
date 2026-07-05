"""
Ambiente de regime permanente: estabiliza em setpoint, aplica perturbação pequena
e calcula métricas de correção (tempo de acomodação, pico de erro, ITAE local).

Tipos de perturbação:
- setpoint: degrau pequeno no setpoint após estabilização
- sensor: bias temporário na leitura do sensor (setpoint constante)
- entrada: pulso na temperatura da água de entrada
"""

from dataclasses import dataclass
from typing import Literal, Optional
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import (
    ConfiguracaoSimulacao,
    MapeamentoPotenciometro,
    ParamsChuveiro,
    ParamsPID,
)
from src.simulation import AmbienteSimulacao

TipoPerturbacao = Literal["setpoint", "sensor", "entrada"]


@dataclass
class MetricasRegimePermanente:
    """Métricas calculadas após a perturbação em regime."""

    t_perturbacao_s: float
    t_acomodacao_s: float
    erro_pico_c: float
    itae_local: float
    oscilacao_erro: float
    erro_final_c: float
    potencia_estavel_w: float
    temperatura_estavel_c: float


def calcular_metricas_pos_perturbacao(
    tempo: np.ndarray,
    erro: np.ndarray,
    potencia_w: np.ndarray,
    temperatura: np.ndarray,
    t_perturbacao: float,
    banda_acomodacao_c: float = 0.2,
    janela_estavel_s: float = 10.0,
) -> MetricasRegimePermanente:
    """
    Calcula indicadores de desempenho a partir do instante da perturbação.

    t_acomodacao_s: tempo relativo até |erro| permanecer abaixo de banda_acomodacao_c.
    """
    mask_pos = tempo >= t_perturbacao
    if not np.any(mask_pos):
        return MetricasRegimePermanente(
            t_perturbacao_s=t_perturbacao,
            t_acomodacao_s=float("inf"),
            erro_pico_c=float("inf"),
            itae_local=float("inf"),
            oscilacao_erro=float("inf"),
            erro_final_c=float("inf"),
            potencia_estavel_w=0.0,
            temperatura_estavel_c=0.0,
        )

    t_rel = tempo[mask_pos] - t_perturbacao
    e_abs = np.abs(erro[mask_pos])
    erro_pico = float(np.max(e_abs))
    itae_local = float(np.trapezoid(t_rel * e_abs, t_rel))

    mask_estavel = tempo < t_perturbacao
    if np.any(mask_estavel):
        t_ini_estavel = max(0.0, t_perturbacao - janela_estavel_s)
        mask_janela = (tempo >= t_ini_estavel) & (tempo < t_perturbacao)
        pot_estavel = float(np.mean(potencia_w[mask_janela]))
        temp_estavel = float(np.mean(temperatura[mask_janela]))
    else:
        pot_estavel = float(potencia_w[0])
        temp_estavel = float(temperatura[0])

    t_acomodacao = float("inf")
    for i in range(len(t_rel)):
        if e_abs[i] <= banda_acomodacao_c:
            if np.all(e_abs[i:] <= banda_acomodacao_c):
                t_acomodacao = float(t_rel[i])
                break

    trecho_final = erro[mask_pos]
    oscilacao = float(np.std(trecho_final[-min(50, len(trecho_final)) :]))
    erro_final = float(erro[mask_pos][-1])

    return MetricasRegimePermanente(
        t_perturbacao_s=t_perturbacao,
        t_acomodacao_s=t_acomodacao,
        erro_pico_c=erro_pico,
        itae_local=itae_local,
        oscilacao_erro=oscilacao,
        erro_final_c=erro_final,
        potencia_estavel_w=pot_estavel,
        temperatura_estavel_c=temp_estavel,
    )


class AmbienteRegimePermanente:
    """
    Simula estabilização em setpoint, perturbação pequena e métricas de correção.

    Usa um único ControladorPID (como no firmware ESP32).
    """

    def __init__(
        self,
        tipo_perturbacao: TipoPerturbacao = "setpoint",
        t_degrau_s: float = 5.0,
        t_perturbacao_s: float = 150.0,
        delta_setpoint_c: float = 0.5,
        bias_sensor_c: float = -0.3,
        duracao_bias_s: float = 5.0,
        delta_entrada_c: float = -1.0,
        duracao_entrada_s: float = 8.0,
        params_chuveiro: Optional[ParamsChuveiro] = None,
        params_pid: Optional[ParamsPID] = None,
        mapeamento_potenciometro: Optional[MapeamentoPotenciometro] = None,
        duracao_s: float = 250.0,
        dt_s: float = 0.1,
        vazao_lmin: float = 2.5,
        banda_acomodacao_c: float = 0.2,
    ):
        self.tipo_perturbacao = tipo_perturbacao
        self.t_degrau_s = t_degrau_s
        self.t_perturbacao_s = t_perturbacao_s
        self.delta_setpoint_c = delta_setpoint_c
        self.bias_sensor_c = bias_sensor_c
        self.duracao_bias_s = duracao_bias_s
        self.delta_entrada_c = delta_entrada_c
        self.duracao_entrada_s = duracao_entrada_s
        self.duracao_s = duracao_s
        self.dt_s = dt_s
        self.vazao_lmin = vazao_lmin
        self.banda_acomodacao_c = banda_acomodacao_c

        self.params_chuveiro = params_chuveiro or ParamsChuveiro()
        self.params_pid = params_pid or ParamsPID(saida_minima=0.0, saida_maxima=1.0)
        self.simulacao = AmbienteSimulacao(
            params_chuveiro=self.params_chuveiro,
            params_pid=self.params_pid,
            mapeamento_potenciometro=mapeamento_potenciometro,
        )

    def obter_configuracao(self) -> ConfiguracaoSimulacao:
        """
        Monta setpoint e callbacks de perturbação.

        A partida segue o mesmo perfil do run_simulation.py:
        setpoint = temperatura_inicial_agua até t_degrau_s, depois temperatura_desejada.
        Só então (em t_perturbacao_s) aplica a perturbação pequena.
        """
        temp_inicial = self.params_chuveiro.temperatura_inicial_agua
        temp_desejada = self.params_chuveiro.temperatura_desejada
        t_degrau = self.t_degrau_s
        t_pert = self.t_perturbacao_s

        def setpoint_funcao(tempo: float) -> float:
            if self.tipo_perturbacao == "setpoint" and tempo >= t_pert:
                return temp_desejada + self.delta_setpoint_c
            if tempo >= t_degrau:
                return temp_desejada
            return temp_inicial

        perturbacao_medicao = None
        perturbacao_entrada = None

        if self.tipo_perturbacao == "sensor":

            def perturbacao_medicao(tempo: float) -> float:
                if t_pert <= tempo < t_pert + self.duracao_bias_s:
                    return self.bias_sensor_c
                return 0.0

        elif self.tipo_perturbacao == "entrada":

            def perturbacao_entrada(tempo: float) -> float:
                if t_pert <= tempo < t_pert + self.duracao_entrada_s:
                    return self.delta_entrada_c
                return 0.0

        return ConfiguracaoSimulacao(
            duracao_s=self.duracao_s,
            dt_s=self.dt_s,
            vazao_lmin=self.vazao_lmin,
            setpoint_funcao=setpoint_funcao,
            perturbacao_medicao=perturbacao_medicao,
            perturbacao_entrada=perturbacao_entrada,
        )

    def executar(
        self, config: Optional[ConfiguracaoSimulacao] = None
    ) -> dict:
        cfg = config or self.obter_configuracao()
        self.simulacao.executar(cfg)
        return self.simulacao.obter_resultados()

    def executar_com_metricas(
        self, config: Optional[ConfiguracaoSimulacao] = None
    ) -> tuple[dict, MetricasRegimePermanente]:
        resultados = self.executar(config)
        metricas = calcular_metricas_pos_perturbacao(
            resultados["tempo"],
            resultados["erro"],
            resultados["potencia_w"],
            resultados["temperatura"],
            t_perturbacao=self.t_perturbacao_s,
            banda_acomodacao_c=self.banda_acomodacao_c,
        )
        resultados["metricas"] = metricas
        return resultados, metricas

    def executar_e_plotar(
        self,
        caminho_base: Optional[str] = None,
        titulo: Optional[str] = None,
        margem_zoom_s: float = 10.0,
    ):
        from src.graficos import Plotador, plotar_regime_zoom

        resultados, metricas = self.executar_com_metricas()
        plotador = Plotador(resultados)
        titulo_plot = titulo or f"Regime permanente ({self.tipo_perturbacao})"
        figuras = plotador.plotar_tudo(
            caminho_base=caminho_base,
            titulo=titulo_plot,
            mostrar_resistencia=False,
        )
        if caminho_base:
            plotar_regime_zoom(
                resultados,
                t_perturbacao=self.t_perturbacao_s,
                margem_antes_s=margem_zoom_s,
                titulo=f"{titulo_plot} — zoom pós-perturbação",
                caminho_salvar=f"{caminho_base}_zoom.png",
            )
        return resultados, metricas, figuras
