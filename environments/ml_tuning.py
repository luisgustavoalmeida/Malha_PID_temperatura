"""
Ambiente para ajuste da malha PID com técnicas de aprendizado de máquina (ou busca em grade).

Define critérios de desempenho:
- Integrais: IAE, ITAE, ISE, ITSE
- Resposta ao degrau: overshoot, undershoot, settling_time, rise_time, peak_time
- Composto: criterio_rapido_estavel (ITAE + overshoot)

Permite testar vários conjuntos (Kp, Ki, Kd). Inclui busca em grade (grid search);
futuramente: otimização bayesiana, reinforcement learning, etc.
"""

from itertools import product
from typing import Optional, List, Tuple, Callable
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, desc="", **kwargs):
        """Fallback sem barra de progresso se tqdm não estiver instalado."""
        return iterable

from src import AmbienteSimulacao, ParamsChuveiro, ParamsPID
from .step_response import AmbienteRespostaDegrau


def criterio_iae(tempo: np.ndarray, erro: np.ndarray) -> float:
    """Integral do valor absoluto do erro (IAE). Quanto menor, melhor."""
    passo = np.diff(tempo, prepend=tempo[0])
    return float(np.sum(np.abs(erro) * passo))


def criterio_itae(tempo: np.ndarray, erro: np.ndarray) -> float:
    """Integral do tempo × valor absoluto do erro (ITAE). Penaliza erros tardios."""
    passo = np.diff(tempo, prepend=tempo[0])
    return float(np.sum(tempo * np.abs(erro) * passo))


def criterio_ise(tempo: np.ndarray, erro: np.ndarray) -> float:
    """Integral do erro ao quadrado (ISE). Penaliza mais erros grandes; quanto menor, melhor."""
    passo = np.diff(tempo, prepend=tempo[0])
    return float(np.sum(erro ** 2 * passo))


def criterio_itse(tempo: np.ndarray, erro: np.ndarray) -> float:
    """Integral do tempo × erro ao quadrado (ITSE). Penaliza erros grandes e tardios; quanto menor, melhor."""
    passo = np.diff(tempo, prepend=tempo[0])
    return float(np.sum(tempo * erro ** 2 * passo))


def criterio_overshoot(
    tempo: np.ndarray,
    erro: np.ndarray,
    setpoint: Optional[np.ndarray] = None,
    temperatura: Optional[np.ndarray] = None,
) -> float:
    """Overshoot percentual após o degrau (quanto a saída ultrapassou o setpoint). Requer setpoint e temperatura."""
    if setpoint is None or temperatura is None or len(tempo) == 0:
        return 0.0
    setpoint_final = setpoint[-1]
    if np.max(temperatura) <= setpoint_final:
        return 0.0
    return float(100.0 * (np.max(temperatura) - setpoint_final) / setpoint_final)


def criterio_rapido_estavel(
    tempo: np.ndarray,
    erro: np.ndarray,
    setpoint: Optional[np.ndarray] = None,
    temperatura: Optional[np.ndarray] = None,
    peso_overshoot: float = 1.0,
) -> float:
    """
    Critério que prioriza resposta rápida e estável: ITAE + penalidade de overshoot.

    - ITAE (Integral do Tempo × |erro|): penaliza erros que demoram a sumir,
      favorecendo atingir a temperatura desejada mais rápido.
    - Overshoot: penaliza ultrapassar o setpoint (instabilidade/oscilação).

    Quanto menor o valor, melhor (resposta mais rápida e estável).
    Aumente peso_overshoot para priorizar mais a estabilidade (menos overshoot).
    """
    itae = criterio_itae(tempo, erro)
    if setpoint is not None and temperatura is not None and peso_overshoot > 0:
        ov = criterio_overshoot(tempo, erro, setpoint=setpoint, temperatura=temperatura)
        return itae + peso_overshoot * ov
    return itae


def criterio_settling_time(
    tempo: np.ndarray,
    erro: np.ndarray,
    setpoint: Optional[np.ndarray] = None,
    temperatura: Optional[np.ndarray] = None,
    banda_pct: float = 2.0,
) -> float:
    """
    Tempo de acomodação [s]: tempo até a saída entrar e permanecer na faixa ±banda_pct% do setpoint.
    Quanto menor, melhor. Requer setpoint e temperatura (senão retorna np.inf).
    """
    if setpoint is None or temperatura is None or len(tempo) == 0:
        return float("inf")
    setpoint_final = float(setpoint[-1])
    if setpoint_final == 0:
        return float("inf")
    banda = banda_pct / 100.0 * abs(setpoint_final)
    dentro = np.abs(temperatura - setpoint_final) <= banda
    # Primeiro índice i a partir do qual a saída permanece na faixa até o fim
    for i in range(len(dentro)):
        if np.all(dentro[i:]):
            return float(tempo[i])
    return float("inf")


def criterio_rise_time(
    tempo: np.ndarray,
    erro: np.ndarray,
    setpoint: Optional[np.ndarray] = None,
    temperatura: Optional[np.ndarray] = None,
) -> float:
    """
    Tempo de subida [s]: tempo para ir de 10% a 90% do valor final (em relação ao degrau).
    Quanto menor, melhor. Requer setpoint e temperatura.
    """
    if setpoint is None or temperatura is None or len(tempo) < 2:
        return float("inf")
    valor_inicial = float(setpoint[0])
    valor_final = float(setpoint[-1])
    delta = valor_final - valor_inicial
    if abs(delta) < 1e-9:
        return 0.0
    v10 = valor_inicial + 0.1 * delta
    v90 = valor_inicial + 0.9 * delta
    t10, t90 = None, None
    for i in range(len(temperatura)):
        if t10 is None and temperatura[i] >= v10:
            t10 = tempo[i]
        if t90 is None and temperatura[i] >= v90:
            t90 = tempo[i]
            break
    if t10 is not None and t90 is not None:
        return float(t90 - t10)
    return float("inf")


def criterio_peak_time(
    tempo: np.ndarray,
    erro: np.ndarray,
    setpoint: Optional[np.ndarray] = None,
    temperatura: Optional[np.ndarray] = None,
) -> float:
    """
    Tempo do pico [s]: instante em que a saída atinge o primeiro máximo (útil para overshoot).
    Quanto menor, melhor. Requer setpoint e temperatura.
    """
    if setpoint is None or temperatura is None or len(tempo) == 0:
        return float("inf")
    idx_max = int(np.argmax(temperatura))
    return float(tempo[idx_max])


def criterio_undershoot(
    tempo: np.ndarray,
    erro: np.ndarray,
    setpoint: Optional[np.ndarray] = None,
    temperatura: Optional[np.ndarray] = None,
) -> float:
    """
    Undershoot percentual: quanto a saída ficou abaixo do valor inicial antes de subir
    (em % do valor final do setpoint). Quanto menor, melhor. Requer setpoint e temperatura.
    """
    if setpoint is None or temperatura is None or len(tempo) == 0:
        return 0.0
    valor_inicial = float(setpoint[0])
    valor_final = float(setpoint[-1])
    minimo = float(np.min(temperatura))
    if minimo >= valor_inicial or abs(valor_final) < 1e-9:
        return 0.0
    return float(100.0 * (valor_inicial - minimo) / abs(valor_final))


class AmbienteTuningML:
    """
    Ambiente para testar vários conjuntos (Kp, Ki, Kd) e escolher o melhor
    segundo um critério (IAE, ITAE, overshoot, etc.).
    """

    def __init__(
        self,
        params_chuveiro: Optional[ParamsChuveiro] = None,
        ambiente_degrau: Optional[AmbienteRespostaDegrau] = None,
        criterio: Callable[..., float] = criterio_iae,
    ):
        self.params_chuveiro = params_chuveiro or ParamsChuveiro()
        self.ambiente_degrau = ambiente_degrau or AmbienteRespostaDegrau(
            params_chuveiro=self.params_chuveiro,
            duracao_s=90.0,
            t_degrau_s=5.0,
        )
        self.criterio = criterio

    def avaliar_pid(
        self, Kp: float, Ki: float, Kd: float
    ) -> Tuple[float, dict]:
        """
        Roda uma simulação com o PID (Kp, Ki, Kd) e retorna (valor_do_criterio, resultados).
        """
        params_pid = ParamsPID(
            Kp=Kp, Ki=Ki, Kd=Kd, saida_minima=0.0, saida_maxima=1.0
        )
        self.ambiente_degrau.params_pid = params_pid
        self.ambiente_degrau.simulacao = AmbienteSimulacao(
            params_chuveiro=self.ambiente_degrau.params_chuveiro,
            params_pid=params_pid,
        )
        resultados = self.ambiente_degrau.executar()
        tempo = resultados["tempo"]
        erro = resultados["erro"]
        valor = self.criterio(tempo, erro)
        return valor, resultados

    def busca_grade(
        self,
        lista_Kp: List[float],
        lista_Ki: List[float],
        lista_Kd: List[float],
        mostrar_progresso: bool = True,
    ) -> List[Tuple[Tuple[float, float, float], float]]:
        """
        Testa todas as combinações de (Kp, Ki, Kd) e retorna lista ordenada
        por valor do critério (menor é melhor para IAE/ITAE).
        Cada elemento é ((Kp, Ki, Kd), valor_criterio).
        Se mostrar_progresso=True, exibe barra de progresso (requer tqdm).
        """
        combinacoes = list(product(lista_Kp, lista_Ki, lista_Kd))
        iterador = tqdm(combinacoes, desc="Busca em grade PID", unit="sim") if mostrar_progresso else combinacoes
        resultados_lista = []
        for Kp, Ki, Kd in iterador:
            valor, _ = self.avaliar_pid(Kp, Ki, Kd)
            resultados_lista.append(((Kp, Ki, Kd), valor))
        resultados_lista.sort(key=lambda x: x[1])
        return resultados_lista
