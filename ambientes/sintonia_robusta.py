"""
Ajuste robusto da malha PID: encontra os melhores (Kp, Ki, Kd) que funcionam bem
em várias condições de operação (temperatura inicial, temperatura desejada,
temperatura ambiente, vazão).

Cada variável é definida por um range (início, fim, passo). A simulação varre
essas combinações e agrega o critério (ex.: IAE) sobre todas as condições
para cada conjunto PID, escolhendo o PID que minimiza a agregação (média ou pior caso).

Suporta processamento em paralelo (multiprocessing) para acelerar a busca.
"""

from dataclasses import dataclass, field
from itertools import product
from typing import Optional, List, Tuple, Callable, Dict, Union
import multiprocessing
import os

# Exceção de timeout do Pool (pode ser multiprocessing.context.TimeoutError no Python 3.12+)
try:
    from multiprocessing.context import TimeoutError as MPTimeoutError
except ImportError:
    MPTimeoutError = TimeoutError  # fallback
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

from src import ParamsChuveiro, ParamsPID
from .resposta_degrau import AmbienteRespostaDegrau
from .sintonia_ml import criterio_iae

# Estado global nos processos worker (preenchido por _worker_init)
_worker_config: Optional[dict] = None
_worker_condicoes: Optional[List[Tuple[float, float, float, float]]] = None


def _worker_init(config: dict, combinacoes_condicoes: List[Tuple[float, float, float, float]]) -> None:
    """Inicializador de cada processo worker: recebe config e lista de condições."""
    global _worker_config, _worker_condicoes
    _worker_config = config
    _worker_condicoes = combinacoes_condicoes


def _worker_avaliar_pid(pid_tuple: Tuple[float, float, float]) -> Union[
    Tuple[Tuple[float, float, float], float],
    Tuple[Tuple[float, float, float], Dict[str, float]],
]:
    """
    Avalia um único (Kp, Ki, Kd) em todas as condições (para execução em processo paralelo).
    Usa _worker_config e _worker_condicoes definidos por _worker_init.
    Se config tem "criterios" (lista (nome, callable)), retorna (pid, {nome: valor_agregado}).
    Se config tem "criterio", retorna (pid, valor) como antes.
    """
    global _worker_config, _worker_condicoes
    Kp, Ki, Kd = pid_tuple
    params_base = _worker_config["params_base"]
    duracao_s = _worker_config["duracao_s"]
    dt_s = _worker_config["dt_s"]
    t_degrau_s = _worker_config["t_degrau_s"]
    agregar = _worker_config["agregar"]

    if "criterios" in _worker_config:
        # Múltiplos critérios: uma simulação por condição, calcula todos os critérios
        criterios_lista = _worker_config["criterios"]  # [(nome, callable), ...]
        por_criterio: Dict[str, List[float]] = {nome: [] for nome, _ in criterios_lista}
        for temp_inicial, temp_desejada, temp_ambiente, vazao in _worker_condicoes:
            params_chuveiro = ParamsChuveiro(
                temperatura_inicial_agua=temp_inicial,
                temperatura_desejada=temp_desejada,
                temperatura_ambiente=temp_ambiente,
                perda_meio=params_base.perda_meio,
                eficiencia_chuveiro=params_base.eficiencia_chuveiro,
                potencia_minima=params_base.potencia_minima,
                potencia_maxima=params_base.potencia_maxima,
                vazao_minima=params_base.vazao_minima,
                vazao_maxima=params_base.vazao_maxima,
                volume_canal=params_base.volume_canal,
            )
            params_pid = ParamsPID(Kp=Kp, Ki=Ki, Kd=Kd, saida_minima=0.0, saida_maxima=1.0)
            ambiente = AmbienteRespostaDegrau(
                params_chuveiro=params_chuveiro,
                params_pid=params_pid,
                t_degrau_s=t_degrau_s,
                duracao_s=duracao_s,
                dt_s=dt_s,
                vazao_lmin=vazao,
            )
            resultados = ambiente.executar()
            tempo = resultados["tempo"]
            erro = resultados["erro"]
            setpoint = resultados.get("setpoint")
            temperatura = resultados.get("temperatura")
            for nome, criterio in criterios_lista:
                try:
                    v = criterio(tempo, erro, setpoint=setpoint, temperatura=temperatura)
                except TypeError:
                    v = criterio(tempo, erro)
                por_criterio[nome].append(v)
        if agregar == "max":
            resultado_dict = {nome: float(np.max(vals)) for nome, vals in por_criterio.items()}
        else:
            resultado_dict = {nome: float(np.mean(vals)) for nome, vals in por_criterio.items()}
        return (pid_tuple, resultado_dict)
    else:
        criterio = _worker_config["criterio"]
        valores = []
        for temp_inicial, temp_desejada, temp_ambiente, vazao in _worker_condicoes:
            params_chuveiro = ParamsChuveiro(
                temperatura_inicial_agua=temp_inicial,
                temperatura_desejada=temp_desejada,
                temperatura_ambiente=temp_ambiente,
                perda_meio=params_base.perda_meio,
                eficiencia_chuveiro=params_base.eficiencia_chuveiro,
                potencia_minima=params_base.potencia_minima,
                potencia_maxima=params_base.potencia_maxima,
                vazao_minima=params_base.vazao_minima,
                vazao_maxima=params_base.vazao_maxima,
                volume_canal=params_base.volume_canal,
            )
            params_pid = ParamsPID(Kp=Kp, Ki=Ki, Kd=Kd, saida_minima=0.0, saida_maxima=1.0)
            ambiente = AmbienteRespostaDegrau(
                params_chuveiro=params_chuveiro,
                params_pid=params_pid,
                t_degrau_s=t_degrau_s,
                duracao_s=duracao_s,
                dt_s=dt_s,
                vazao_lmin=vazao,
            )
            resultados = ambiente.executar()
            tempo = resultados["tempo"]
            erro = resultados["erro"]
            setpoint = resultados.get("setpoint")
            temperatura = resultados.get("temperatura")
            try:
                v = criterio(tempo, erro, setpoint=setpoint, temperatura=temperatura)
            except TypeError:
                v = criterio(tempo, erro)
            valores.append(v)
        valor_agg = float(np.max(valores)) if agregar == "max" else float(np.mean(valores))
        return (pid_tuple, valor_agg)


def _gerar_valores(inicio: float, fim: float, passo: float) -> List[float]:
    """
    Gera lista de valores de inicio a fim (inclusivo) com passo dado.
    Se passo <= 0 ou fim < inicio, retorna [inicio].
    """
    if passo <= 0 or fim < inicio:
        return [inicio]
    n = int(round((fim - inicio) / passo)) + 1
    n = max(1, n)
    valores = list(np.linspace(inicio, fim, n))
    return valores


@dataclass
class RangeVar:
    """Range para uma variável: início, fim e passo."""

    inicio: float
    fim: float
    passo: float

    def gerar(self) -> List[float]:
        """Retorna lista de valores no range [inicio, fim] com passo."""
        return _gerar_valores(self.inicio, self.fim, self.passo)


@dataclass
class RangesTuningRobusto:
    """
    Ranges (início, fim, passo) para cada variável do tuning robusto.
    Ajuste inicio, fim e passo conforme a necessidade da simulação.
    """

    # Condições de operação
    temperatura_inicial_agua: RangeVar = field(
        default_factory=lambda: RangeVar(inicio=15.0, fim=20.0, passo=2.0)
    )
    temperatura_desejada: RangeVar = field(
        default_factory=lambda: RangeVar(inicio=36.0, fim=38.0, passo=0.25)
    )
    temperatura_ambiente: RangeVar = field(
        default_factory=lambda: RangeVar(inicio=18.0, fim=20.0, passo=5.0)
    )
    vazao_lmin: RangeVar = field(
        default_factory=lambda: RangeVar(inicio=2.4, fim=5.0, passo=2.5)
    )

    # Ganhos do PID
    Kp: RangeVar = field(default_factory=lambda: RangeVar(inicio=0.000, fim=0.9, passo=0.01))
    Ki: RangeVar = field(default_factory=lambda: RangeVar(inicio=0.000, fim=0.02, passo=0.001))
    Kd: RangeVar = field(default_factory=lambda: RangeVar(inicio=0.000, fim=0.9, passo=0.01))

    def gerar_condicoes(self) -> List[Tuple[float, float, float, float]]:
        """Gera todas as combinações (temp_inicial, temp_desejada, temp_ambiente, vazao)."""
        ti = self.temperatura_inicial_agua.gerar()
        td = self.temperatura_desejada.gerar()
        ta = self.temperatura_ambiente.gerar()
        v = self.vazao_lmin.gerar()
        return list(product(ti, td, ta, v))

    def gerar_pid(self) -> List[Tuple[float, float, float]]:
        """Gera todas as combinações (Kp, Ki, Kd)."""
        kp = self.Kp.gerar()
        ki = self.Ki.gerar()
        kd = self.Kd.gerar()
        return list(product(kp, ki, kd))


class TuningRobusto:
    """
    Avalia cada conjunto (Kp, Ki, Kd) em várias condições de operação e
    agrega o critério (ex.: IAE) para encontrar o PID mais robusto.
    """

    def __init__(
        self,
        params_chuveiro_base: Optional[ParamsChuveiro] = None,
        ranges: Optional[RangesTuningRobusto] = None,
        duracao_s: float = 120.0,
        dt_s: float = 0.1,
        t_degrau_s: float = 10.0,
        criterio: Optional[Callable[..., float]] = None,
        criterios: Optional[Dict[str, Callable[..., float]]] = None,
        agregar: str = "media",  # "media" ou "max" (pior caso)
    ):
        """
        params_chuveiro_base: parâmetros fixos do chuveiro (potência, eficiência, etc.);
          temperatura e vazão são sobrescritos por cada condição.
        ranges: ranges para variar; se None, usa RangesTuningRobusto().
        criterio: critério único (quanto menor, melhor). Usado se criterios for None.
        criterios: se informado, avalia todos os critérios em uma única passada e
          executar() retorna dict[nome, ranking]. Ignora criterio quando presente.
        agregar: "media" = média do critério sobre condições; "max" = pior caso.
        """
        self.params_base = params_chuveiro_base or ParamsChuveiro()
        self.ranges = ranges or RangesTuningRobusto()
        self.duracao_s = duracao_s
        self.dt_s = dt_s
        self.t_degrau_s = t_degrau_s
        self.criterio = criterio if criterio is not None else criterio_iae
        self.criterios = criterios  # dict nome -> callable; se não None, executar() retorna rankings por categoria
        self.agregar = agregar

    def _simular_uma_condicao(
        self,
        temp_inicial: float,
        temp_desejada: float,
        temp_ambiente: float,
        vazao_lmin: float,
        Kp: float,
        Ki: float,
        Kd: float,
    ) -> float:
        """Roda uma simulação para uma condição e um PID; retorna valor do critério (ex.: IAE)."""
        params_chuveiro = ParamsChuveiro(
            temperatura_inicial_agua=temp_inicial,
            temperatura_desejada=temp_desejada,
            temperatura_ambiente=temp_ambiente,
            perda_meio=self.params_base.perda_meio,
            eficiencia_chuveiro=self.params_base.eficiencia_chuveiro,
            potencia_minima=self.params_base.potencia_minima,
            potencia_maxima=self.params_base.potencia_maxima,
            vazao_minima=self.params_base.vazao_minima,
            vazao_maxima=self.params_base.vazao_maxima,
            volume_canal=self.params_base.volume_canal,
        )
        params_pid = ParamsPID(Kp=Kp, Ki=Ki, Kd=Kd, saida_minima=0.0, saida_maxima=1.0)
        ambiente = AmbienteRespostaDegrau(
            params_chuveiro=params_chuveiro,
            params_pid=params_pid,
            t_degrau_s=self.t_degrau_s,
            duracao_s=self.duracao_s,
            dt_s=self.dt_s,
            vazao_lmin=vazao_lmin,
        )
        resultados = ambiente.executar()
        tempo = resultados["tempo"]
        erro = resultados["erro"]
        setpoint = resultados.get("setpoint")
        temperatura = resultados.get("temperatura")
        # Critérios que usam setpoint/temperatura (ex.: criterio_rapido_estavel) recebem os dados
        try:
            return self.criterio(tempo, erro, setpoint=setpoint, temperatura=temperatura)
        except TypeError:
            return self.criterio(tempo, erro)

    def avaliar_pid_robusto(
        self,
        Kp: float,
        Ki: float,
        Kd: float,
        combinacoes_condicoes: List[Tuple[float, float, float, float]],
    ) -> float:
        """
        Para um dado (Kp, Ki, Kd), roda a simulação para todas as condições
        e retorna o valor agregado (média ou max) do critério.
        """
        valores = []
        for temp_inicial, temp_desejada, temp_ambiente, vazao in combinacoes_condicoes:
            v = self._simular_uma_condicao(
                temp_inicial, temp_desejada, temp_ambiente, vazao, Kp, Ki, Kd
            )
            valores.append(v)
        if self.agregar == "max":
            return float(np.max(valores))
        return float(np.mean(valores))

    def avaliar_pid_robusto_multi(
        self,
        Kp: float,
        Ki: float,
        Kd: float,
        combinacoes_condicoes: List[Tuple[float, float, float, float]],
        criterios_dict: Dict[str, Callable[..., float]],
    ) -> Dict[str, float]:
        """
        Para um dado (Kp, Ki, Kd), roda a simulação para todas as condições
        e retorna um dict { nome_criterio: valor_agregado } para cada critério.
        """
        por_criterio: Dict[str, List[float]] = {nome: [] for nome in criterios_dict}
        for temp_inicial, temp_desejada, temp_ambiente, vazao in combinacoes_condicoes:
            params_chuveiro = ParamsChuveiro(
                temperatura_inicial_agua=temp_inicial,
                temperatura_desejada=temp_desejada,
                temperatura_ambiente=temp_ambiente,
                perda_meio=self.params_base.perda_meio,
                eficiencia_chuveiro=self.params_base.eficiencia_chuveiro,
                potencia_minima=self.params_base.potencia_minima,
                potencia_maxima=self.params_base.potencia_maxima,
                vazao_minima=self.params_base.vazao_minima,
                vazao_maxima=self.params_base.vazao_maxima,
                volume_canal=self.params_base.volume_canal,
            )
            params_pid = ParamsPID(Kp=Kp, Ki=Ki, Kd=Kd, saida_minima=0.0, saida_maxima=1.0)
            ambiente = AmbienteRespostaDegrau(
                params_chuveiro=params_chuveiro,
                params_pid=params_pid,
                t_degrau_s=self.t_degrau_s,
                duracao_s=self.duracao_s,
                dt_s=self.dt_s,
                vazao_lmin=vazao,
            )
            resultados = ambiente.executar()
            tempo = resultados["tempo"]
            erro = resultados["erro"]
            setpoint = resultados.get("setpoint")
            temperatura = resultados.get("temperatura")
            for nome, criterio in criterios_dict.items():
                try:
                    v = criterio(tempo, erro, setpoint=setpoint, temperatura=temperatura)
                except TypeError:
                    v = criterio(tempo, erro)
                por_criterio[nome].append(v)
        if self.agregar == "max":
            return {nome: float(np.max(vals)) for nome, vals in por_criterio.items()}
        return {nome: float(np.mean(vals)) for nome, vals in por_criterio.items()}

    def executar(
        self,
        mostrar_progresso: bool = True,
        num_workers: Optional[int] = None,
    ) -> Union[
        List[Tuple[Tuple[float, float, float], float]],
        Dict[str, List[Tuple[Tuple[float, float, float], float]]],
    ]:
        """
        Varre todos os (Kp, Ki, Kd) e, para cada um, avalia em todas as condições.
        Se criterios foi informado no __init__: retorna dict[nome_criterio, ranking],
        onde cada ranking é lista [((Kp, Ki, Kd), valor), ...] ordenada (menor é melhor).
        Caso contrário: retorna lista única [((Kp, Ki, Kd), valor), ...].

        num_workers: número de processos paralelos; None = os.cpu_count() - 1 (mín. 1);
                    1 = execução em série (sem multiprocessing).
        """
        combinacoes_condicoes = self.ranges.gerar_condicoes()
        combinacoes_pid = self.ranges.gerar_pid()
        multi = self.criterios is not None and len(self.criterios) > 0
        nomes_criterios = list(self.criterios.keys()) if multi else []

        if num_workers is None:
            n_cpu = os.cpu_count() or 4
            num_workers = max(1, n_cpu - 1)
        num_workers = max(1, int(num_workers))

        if num_workers == 1:
            # Execução em série
            resultados_lista: List[Tuple[Tuple[float, float, float], Union[float, Dict[str, float]]]] = []
            iterador_pid = (
                tqdm(combinacoes_pid, desc="Tuning robusto (PID)", unit="pid")
                if mostrar_progresso
                else combinacoes_pid
            )
            for Kp, Ki, Kd in iterador_pid:
                pid_tuple = (Kp, Ki, Kd)
                if multi:
                    d = self.avaliar_pid_robusto_multi(
                        Kp, Ki, Kd, combinacoes_condicoes, self.criterios
                    )
                    resultados_lista.append((pid_tuple, d))
                else:
                    valor_agg = self.avaliar_pid_robusto(Kp, Ki, Kd, combinacoes_condicoes)
                    resultados_lista.append((pid_tuple, valor_agg))
        else:
            timeout_por_pid = 120
            if mostrar_progresso:
                print(f"  Usando {num_workers} processos em paralelo (timeout {timeout_por_pid}s por PID).")
            if multi:
                criterios_lista = [(nome, self.criterios[nome]) for nome in nomes_criterios]
                config = {
                    "params_base": self.params_base,
                    "duracao_s": self.duracao_s,
                    "dt_s": self.dt_s,
                    "t_degrau_s": self.t_degrau_s,
                    "criterios": criterios_lista,
                    "agregar": self.agregar,
                }
            else:
                config = {
                    "params_base": self.params_base,
                    "duracao_s": self.duracao_s,
                    "dt_s": self.dt_s,
                    "t_degrau_s": self.t_degrau_s,
                    "criterio": self.criterio,
                    "agregar": self.agregar,
                }
            with multiprocessing.Pool(
                processes=num_workers,
                initializer=_worker_init,
                initargs=(config, combinacoes_condicoes),
            ) as pool:
                futures = [
                    pool.apply_async(_worker_avaliar_pid, (pid,))
                    for pid in combinacoes_pid
                ]
                resultados_lista = []
                iterador = (
                    tqdm(
                        zip(combinacoes_pid, futures),
                        total=len(combinacoes_pid),
                        desc="Tuning robusto (PID)",
                        unit="pid",
                    )
                    if mostrar_progresso
                    else zip(combinacoes_pid, futures)
                )
                for pid_tuple, future in iterador:
                    try:
                        resultado = future.get(timeout=timeout_por_pid)
                    except (TimeoutError, MPTimeoutError):
                        if multi:
                            resultado = (pid_tuple, {n: float("inf") for n in nomes_criterios})
                        else:
                            resultado = (pid_tuple, float("inf"))
                    resultados_lista.append(resultado)

        if multi:
            ranking_por_criterio: Dict[str, List[Tuple[Tuple[float, float, float], float]]] = {}
            for nome in nomes_criterios:
                lista = [(pid, d[nome]) for pid, d in resultados_lista]
                lista.sort(key=lambda x: x[1])
                ranking_por_criterio[nome] = lista
            return ranking_por_criterio
        else:
            resultados_lista.sort(key=lambda x: x[1])  # type: ignore[arg-type]
            return resultados_lista  # type: ignore[return-value]
