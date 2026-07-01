"""
Controlador PID com anti-windup e saturação de saída.

A saída do PID é um sinal normalizado (0 a 1) que representa a potência desejada.
O mapeamento para o potenciômetro de 50 kΩ (e para o ESP32) é feito em potenciometro.py.
"""

from dataclasses import dataclass
from typing import Literal, Optional

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


CriterioTrocaRegime = Literal["erro", "tempo", "hibrido"]


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

    def trocar_ganhos_sem_salto(
        self,
        novos_params: ParamsPID,
        erro: float,
        passo_tempo: float,
    ) -> None:
        """
        Substitui Kp/Ki/Kd mantendo a contribuição integral na saída (anti-bump).
        Preserva _ultimo_erro e _ultimo_tempo para continuidade do termo D.
        """
        acao_i = self.params.Ki * self._integral
        self.params = novos_params
        self._integral_maxima = _calcular_integral_maxima(self.params)
        if self.params.Ki > 1e-9:
            self._integral = acao_i / self.params.Ki
        else:
            acao_p = self.params.Kp * erro
            acao_d = 0.0
            if self._ultimo_erro is not None and passo_tempo > 0:
                acao_d = self.params.Kd * (erro - self._ultimo_erro) / passo_tempo
            acao_alvo = np.clip(
                acao_p + acao_i + acao_d,
                self.params.saida_minima,
                self.params.saida_maxima,
            )
            self._integral = 0.0
            if self.params.Ki > 1e-9:
                self._integral = (acao_alvo - acao_p - acao_d) / self.params.Ki
        self._integral = float(
            np.clip(self._integral, -self._integral_maxima, self._integral_maxima)
        )

    def definir_limites(self, saida_minima: float, saida_maxima: float) -> None:
        """
        Altera os limites de saturação da saída e recalcula o limite da integral (anti-windup).
        Útil para reconfigurar o controlador em tempo de execução (ex.: modos econômico/normal).
        """
        self.params.saida_minima = saida_minima
        self.params.saida_maxima = saida_maxima
        self._integral_maxima = _calcular_integral_maxima(self.params)


class ControladorPIDComAgendamento:
    """
    Um único PID: ganhos de partida até a troca; depois ganhos de regime.
    Mantém integral/estado internos — troca sem vale na potência (bumpless).
    """

    def __init__(
        self,
        params_partida: ParamsPID,
        params_regime: ParamsPID,
        t_troca_regime_s: Optional[float] = None,
        criterio_troca: CriterioTrocaRegime = "tempo",
        limiar_partida: float = 2.0,
        limiar_regime: float = 0.8,
    ):
        if criterio_troca == "tempo" and t_troca_regime_s is None:
            raise ValueError("criterio_troca='tempo' exige t_troca_regime_s definido")
        if limiar_regime >= limiar_partida:
            raise ValueError("limiar_regime deve ser menor que limiar_partida")
        self.params_partida = params_partida
        self.params_regime = params_regime
        self.t_troca_regime_s = t_troca_regime_s
        self.criterio_troca = criterio_troca
        self.limiar_partida = limiar_partida
        self.limiar_regime = limiar_regime
        self.pid = ControladorPID(params_partida)
        self._fase: str = "partida"

    @property
    def params(self) -> ParamsPID:
        return self.pid.params

    @property
    def modo_atual(self) -> str:
        return self._fase

    def reiniciar(self) -> None:
        self.pid = ControladorPID(self.params_partida)
        self._fase = "partida"

    def _passo_tempo(self, tempo_atual: float) -> float:
        if self.pid._ultimo_tempo is None:
            return 1e-6
        dt = tempo_atual - self.pid._ultimo_tempo
        return dt if dt > 0 else 1e-6

    def _deve_trocar_para_regime(self, erro: float, tempo_atual: float) -> bool:
        if self._fase == "regime":
            return False
        if self.criterio_troca == "tempo":
            return (
                self.t_troca_regime_s is not None
                and tempo_atual >= self.t_troca_regime_s
            )
        if self.criterio_troca == "hibrido":
            if (
                self.t_troca_regime_s is not None
                and tempo_atual >= self.t_troca_regime_s
            ):
                return True
            return abs(erro) < self.limiar_regime
        return abs(erro) < self.limiar_regime

    def _deve_trocar_para_partida(self, erro: float) -> bool:
        if self._fase != "regime":
            return False
        if self.criterio_troca == "tempo":
            return False
        return abs(erro) > self.limiar_partida

    def passo(
        self, valor_desejado: float, valor_medido: float, tempo_atual: float
    ) -> float:
        erro = valor_desejado - valor_medido
        dt = self._passo_tempo(tempo_atual)

        if self._deve_trocar_para_regime(erro, tempo_atual):
            self.pid.trocar_ganhos_sem_salto(self.params_regime, erro, dt)
            self._fase = "regime"
        elif self._deve_trocar_para_partida(erro):
            self.pid.trocar_ganhos_sem_salto(self.params_partida, erro, dt)
            self._fase = "partida"

        return self.pid.passo(valor_desejado, valor_medido, tempo_atual)


class ControladorPIDDual:
    """
    Dois PIDs com troca configurável entre malha de partida e malha de regime.

    Criterio de troca (criterio_troca):
    - "erro": histerese em |erro| (limiar_regime / limiar_partida)
    - "tempo": malha de partida antes de t_troca_regime_s; regime depois
    - "hibrido": troca em t_troca_regime_s OU por |erro|; volta a partida se |erro| > limiar_partida
    """

    def __init__(
        self,
        params_partida: ParamsPID,
        params_regime: ParamsPID,
        limiar_partida: float = 2.0,
        limiar_regime: float = 0.8,
        t_troca_regime_s: Optional[float] = None,
        criterio_troca: CriterioTrocaRegime = "erro",
    ):
        if limiar_regime >= limiar_partida:
            raise ValueError("limiar_regime deve ser menor que limiar_partida")
        if criterio_troca == "tempo" and t_troca_regime_s is None:
            raise ValueError("criterio_troca='tempo' exige t_troca_regime_s definido")
        self.params_partida = params_partida
        self.params_regime = params_regime
        self.limiar_partida = limiar_partida
        self.limiar_regime = limiar_regime
        self.t_troca_regime_s = t_troca_regime_s
        self.criterio_troca = criterio_troca
        self.pid_partida = ControladorPID(params_partida)
        self.pid_regime = ControladorPID(params_regime)
        self._modo: str = "partida"

    @property
    def params(self) -> ParamsPID:
        """Parâmetros do PID ativo (compatibilidade com AmbienteSimulacao)."""
        if self._modo == "partida":
            return self.params_partida
        return self.params_regime

    @property
    def modo_atual(self) -> str:
        return self._modo

    def reiniciar(self) -> None:
        self.pid_partida.reiniciar()
        self.pid_regime.reiniciar()
        self._modo = "partida"

    def _atualizar_modo(self, erro: float, tempo_atual: float) -> None:
        if self.criterio_troca == "tempo":
            if (
                self.t_troca_regime_s is not None
                and tempo_atual >= self.t_troca_regime_s
            ):
                self._modo = "regime"
            else:
                self._modo = "partida"
            return

        if self.criterio_troca == "hibrido":
            if (
                self.t_troca_regime_s is not None
                and tempo_atual >= self.t_troca_regime_s
            ):
                self._modo = "regime"

        if self._modo == "partida":
            if abs(erro) < self.limiar_regime:
                self._modo = "regime"
        elif abs(erro) > self.limiar_partida:
            self._modo = "partida"

    def passo(
        self, valor_desejado: float, valor_medido: float, tempo_atual: float
    ) -> float:
        erro = valor_desejado - valor_medido
        self._atualizar_modo(erro, tempo_atual)

        if self._modo == "partida":
            return self.pid_partida.passo(valor_desejado, valor_medido, tempo_atual)
        return self.pid_regime.passo(valor_desejado, valor_medido, tempo_atual)
