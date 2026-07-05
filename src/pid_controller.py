"""
Controlador PID com anti-windup e saturação de saída.

Espelha pid_controller.cpp do firmware ESP32 (Controle_temperatura_ESP32).
Saída normalizada 0..1 → potência no dimmer / potenciômetro.
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np


def _calcular_integral_maxima(params_pid: "ParamsPID") -> float:
    """Limite da integral: (saida_max − saida_min) / Ki, ou integral_maxima se definido."""
    if params_pid.integral_maxima is not None:
        return params_pid.integral_maxima
    ki = max(1e-9, params_pid.Ki)
    return (params_pid.saida_maxima - params_pid.saida_minima) / ki


@dataclass
class ParamsPID:
    """
    Ganhos e limites do controlador PID.

    Termo D: −Kd × d(PV)/dt (derivada na medida, sem derivative kick em setpoint).
    """

    Kp: float = 1.0
    Ki: float = 0.1
    Kd: float = 0.05
    saida_minima: float = 0.0
    saida_maxima: float = 1.0
    integral_maxima: Optional[float] = None


class ControladorPID:
    """
    Controlador PID — algoritmo idêntico ao ControladorPID do ESP32.

    Inclui sincronizar_integral_para_saida() para transferência suave de setpoint.
    """

    def __init__(self, params: Optional[ParamsPID] = None):
        self.params = params or ParamsPID()
        self._integral: float = 0.0
        self._integral_maxima = _calcular_integral_maxima(self.params)
        self._ultimo_erro: float = 0.0
        self._ultimo_valor_medido: float = 0.0
        self._ultimo_termo_p: float = 0.0
        self._ultimo_termo_i: float = 0.0
        self._ultimo_termo_d: float = 0.0
        self._ultimo_tempo: Optional[float] = None
        self._primeiro_passo: bool = True

    def reiniciar(self) -> None:
        """Zera integral e histórico (equivalente a reiniciar() no C++)."""
        self._integral = 0.0
        self._ultimo_erro = 0.0
        self._ultimo_valor_medido = 0.0
        self._ultimo_tempo = None
        self._primeiro_passo = True

    def sincronizar_integral_para_saida(
        self,
        saida: float,
        valor_desejado: float,
        valor_medido: float,
    ) -> None:
        """
        Ajusta a integral para manter a saída atual após mudança de setpoint
        (transferência sem choque — espelha sincronizarIntegralParaSaida() do ESP32).
        """
        erro = valor_desejado - valor_medido
        termo_p = self.params.Kp * erro
        ki = max(1e-9, self.params.Ki)
        self._integral = (saida - termo_p - self._ultimo_termo_d) / ki
        self._integral = float(
            np.clip(self._integral, -self._integral_maxima, self._integral_maxima)
        )
        self._ultimo_erro = erro
        self._ultimo_termo_i = self.params.Ki * self._integral

    def passo(
        self, valor_desejado: float, valor_medido: float, tempo_atual: float
    ) -> float:
        """
        Um passo do controlador (equivalente a passo() no C++).

        Retorna saída limitada entre saida_minima e saida_maxima.
        """
        erro = valor_desejado - valor_medido

        delta_t = 1e-6
        if not self._primeiro_passo and self._ultimo_tempo is not None:
            delta_t = tempo_atual - self._ultimo_tempo
            if delta_t <= 0:
                delta_t = 1e-6

        termo_p = self.params.Kp * erro

        self._integral += erro * delta_t
        self._integral = float(
            np.clip(self._integral, -self._integral_maxima, self._integral_maxima)
        )
        termo_i = self.params.Ki * self._integral

        termo_d = 0.0
        if not self._primeiro_passo:
            derivada_medida = (valor_medido - self._ultimo_valor_medido) / delta_t
            termo_d = -self.params.Kd * derivada_medida

        self._ultimo_erro = erro
        self._ultimo_valor_medido = valor_medido
        self._ultimo_termo_p = termo_p
        self._ultimo_termo_i = termo_i
        self._ultimo_termo_d = termo_d
        self._ultimo_tempo = tempo_atual
        self._primeiro_passo = False

        acao_bruta = termo_p + termo_i + termo_d
        acao_limitada = float(
            np.clip(acao_bruta, self.params.saida_minima, self.params.saida_maxima)
        )

        if abs(acao_bruta - acao_limitada) > 1e-9:
            ki = max(1e-9, self.params.Ki)
            self._integral -= (acao_bruta - acao_limitada) / ki
            self._integral = float(
                np.clip(self._integral, -self._integral_maxima, self._integral_maxima)
            )

        return acao_limitada

    @property
    def ultimo_erro(self) -> float:
        return self._ultimo_erro

    @property
    def ultimo_termo_p(self) -> float:
        return self._ultimo_termo_p

    @property
    def ultimo_termo_i(self) -> float:
        return self._ultimo_termo_i

    @property
    def ultimo_termo_d(self) -> float:
        return self._ultimo_termo_d

    def definir_limites(self, saida_minima: float, saida_maxima: float) -> None:
        """Altera limites de saída e recalcula teto da integral."""
        self.params.saida_minima = saida_minima
        self.params.saida_maxima = saida_maxima
        self._integral_maxima = _calcular_integral_maxima(self.params)
