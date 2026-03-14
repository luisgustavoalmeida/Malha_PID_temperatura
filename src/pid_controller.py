"""
Controlador PID com anti-windup e saturação de saída.

A saída do PID é um sinal normalizado (0 a 1) que representa a potência desejada.
O mapeamento para o potenciômetro de 50 kΩ (e para o ESP32) é feito em potenciometro.py.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np


def _calcular_integral_maxima(params_pid: "ParamsPID") -> float:
    """
    Calcula o limite da ação integral para anti-windup.
    Se integral_max não for definido, usa (saida_maxima - saida_minima) / Ki.
    """
    if params_pid.integral_maxima is not None:
        return params_pid.integral_maxima
    return (params_pid.saida_maxima - params_pid.saida_minima) / max(
        1e-9, params_pid.Ki
    )


@dataclass
class ParamsPID:
    """
    Ganhos e limites do controlador PID.

    - Kp, Ki, Kd: ganhos proporcional, integral e derivativo.
    - saida_minima, saida_maxima: saturação da ação de controle (ex.: 0 e 1).
    - integral_maxima: limite do termo integral (anti-windup); None = automático.
    """

    Kp: float = 1.0
    Ki: float = 0.1
    Kd: float = 0.05
    saida_minima: float = 0.0
    saida_maxima: float = 1.0
    integral_maxima: Optional[float] = None


class ControladorPID:
    """
    Controlador PID com saída limitada e anti-windup (back-calculation).
    A saída é interpretada como potência normalizada (0 a 1).
    """

    def __init__(self, params: Optional[ParamsPID] = None):
        self.params = params or ParamsPID()
        self._integral: float = 0.0
        self._ultimo_erro: Optional[float] = None
        self._ultimo_tempo: Optional[float] = None
        self._integral_maxima = _calcular_integral_maxima(self.params)

    def reiniciar(self) -> None:
        """Zera o estado interno do PID (integral e último erro/tempo)."""
        self._integral = 0.0
        self._ultimo_erro = None
        self._ultimo_tempo = None

    def passo(
        self, valor_desejado: float, valor_medido: float, tempo_atual: float
    ) -> float:
        """
        Calcula a ação de controle em um instante.

        Argumentos:
            valor_desejado: setpoint de temperatura [°C]
            valor_medido: temperatura medida pelo sensor na saída [°C]
            tempo_atual: tempo atual da simulação [s]

        Retorna:
            Ação de controle limitada entre saida_minima e saida_maxima (ex.: 0 a 1).
        """
        erro = valor_desejado - valor_medido

        passo_tempo = 0.0
        if self._ultimo_tempo is not None:
            passo_tempo = tempo_atual - self._ultimo_tempo
        if passo_tempo <= 0:
            passo_tempo = 1e-6

        # Termo proporcional
        acao_p = self.params.Kp * erro

        # Termo integral com anti-windup (limite na integral)
        self._integral += erro * passo_tempo
        self._integral = np.clip(
            self._integral, -self._integral_maxima, self._integral_maxima
        )
        acao_i = self.params.Ki * self._integral

        # Termo derivativo (derivada do erro no tempo)
        if self._ultimo_erro is not None:
            derivada_erro = (erro - self._ultimo_erro) / passo_tempo
            acao_d = self.params.Kd * derivada_erro
        else:
            acao_d = 0.0

        self._ultimo_erro = erro
        self._ultimo_tempo = tempo_atual

        acao = acao_p + acao_i + acao_d
        acao_limite = np.clip(acao, self.params.saida_minima, self.params.saida_maxima)

        # Anti-windup por back-calculation: reduz a integral quando a saída satura
        if acao != acao_limite:
            self._integral -= (acao - acao_limite) / max(1e-9, self.params.Ki)
            self._integral = np.clip(
                self._integral, -self._integral_maxima, self._integral_maxima
            )

        return float(acao_limite)

    def definir_limites(self, saida_minima: float, saida_maxima: float) -> None:
        """
        Altera os limites de saturação da saída e recalcula o limite da integral (anti-windup).
        Útil para reconfigurar o controlador em tempo de execução (ex.: modos econômico/normal).
        """
        self.params.saida_minima = saida_minima
        self.params.saida_maxima = saida_maxima
        self._integral_maxima = _calcular_integral_maxima(self.params)
