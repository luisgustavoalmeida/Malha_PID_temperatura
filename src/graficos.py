"""
Visualização da resposta do chuveiro e do comportamento da malha de controle.

Gera gráficos de temperatura (setpoint vs saída), ação de controle (potência) e
resistência do potenciômetro para análise e documentação.
"""

from pathlib import Path
from typing import Optional, Dict
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

# Backend não interativo por padrão; pode mudar para QtAgg em ambiente com display
matplotlib.use("Agg")


def _configurar_eixos(
    eixos: plt.Axes, titulo: str, rotulo_x: str = "Tempo (s)"
) -> None:
    """Aplica título, rótulo do eixo x e grade ao eixo."""
    eixos.set_title(titulo)
    eixos.set_xlabel(rotulo_x)
    eixos.grid(True, alpha=0.3)
    eixos.legend(loc="best", fontsize=8)


def plotar_resposta(
    tempo: np.ndarray,
    setpoint: np.ndarray,
    temperatura: np.ndarray,
    potencia_norm: Optional[np.ndarray] = None,
    resistencia_ohm: Optional[np.ndarray] = None,
    titulo: str = "Resposta da malha PID - Chuveiro",
    tamanho_figura: tuple = (10, 8),
    caminho_salvar: Optional[str] = None,
) -> plt.Figure:
    """
    Gera figura com um ou mais subgráficos:
    - Temperatura: setpoint vs temperatura de saída
    - (Opcional) Potência normalizada [%]
    - (Opcional) Resistência do potenciômetro [kΩ] para ESP32
    """
    numero_graficos = 1
    if potencia_norm is not None:
        numero_graficos += 1
    if resistencia_ohm is not None:
        numero_graficos += 1

    fig, lista_eixos = plt.subplots(
        numero_graficos, 1, sharex=True, figsize=tamanho_figura
    )
    if numero_graficos == 1:
        lista_eixos = [lista_eixos]

    # Gráfico de temperatura: escala Y baseada nos dados com margem
    eixo0 = lista_eixos[0]
    eixo0.plot(tempo, setpoint, label="Setpoint (°C)", color="C1", linestyle="--")
    eixo0.plot(tempo, temperatura, label="Temperatura saída (°C)", color="C0")
    eixo0.set_ylabel("Temperatura (°C)")
    # Ajustar escala do eixo Y para refletir os dados (setpoint e temperatura) com margem
    y_min_dados = float(min(setpoint.min(), temperatura.min()))
    y_max_dados = float(max(setpoint.max(), temperatura.max()))
    margem = max(2.0, (y_max_dados - y_min_dados) * 0.15)  # pelo menos 2 °C ou 15% do intervalo
    intervalo_minimo = 10.0  # evita escala muito comprimida
    y_min = y_min_dados - margem
    y_max = y_max_dados + margem
    if y_max - y_min < intervalo_minimo:
        centro = (y_min + y_max) / 2.0
        y_min = centro - intervalo_minimo / 2.0
        y_max = centro + intervalo_minimo / 2.0
    eixo0.set_ylim(y_min, y_max)
    # Marcas do eixo em valores "redondos" (múltiplos de 5)
    eixo0.yaxis.set_major_locator(MaxNLocator(integer=False, prune="both", nbins=8))
    _configurar_eixos(eixo0, "Temperatura")

    indice = 1
    if potencia_norm is not None:
        lista_eixos[indice].plot(
            tempo, potencia_norm * 100, label="Potência (%)", color="C2"
        )
        lista_eixos[indice].set_ylabel("Potência (%)")
        lista_eixos[indice].set_ylim(-5, 105)
        _configurar_eixos(
            lista_eixos[indice], "Ação de controle (potência)"
        )
        indice += 1
    if resistencia_ohm is not None:
        lista_eixos[indice].plot(
            tempo, resistencia_ohm / 1e3, label="Resistência (kΩ)", color="C3"
        )
        lista_eixos[indice].set_ylabel("Resistência (kΩ)")
        _configurar_eixos(
            lista_eixos[indice], "Potenciômetro 50k (para ESP32)"
        )

    # Exibir valores do eixo tempo (s) em todos os subgráficos
    for eixos in lista_eixos:
        eixos.tick_params(axis="x", labelbottom=True)
        eixos.set_xlabel("Tempo (s)")

    fig.suptitle(titulo, fontsize=12)
    plt.tight_layout()
    if caminho_salvar:
        Path(caminho_salvar).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(caminho_salvar, dpi=150, bbox_inches="tight")
    return fig


def plotar_erro(
    tempo: np.ndarray,
    erro: np.ndarray,
    titulo: str = "Erro de controle",
    caminho_salvar: Optional[str] = None,
    linhas_verticais: Optional[list] = None,
) -> plt.Figure:
    """Gera gráfico do erro (setpoint - temperatura de saída) ao longo do tempo."""
    fig, eixos = plt.subplots(1, 1, figsize=(8, 3))
    eixos.plot(tempo, erro, color="C4", label="Erro (setpoint - saída)")
    eixos.axhline(0, color="gray", linestyle="--")
    if linhas_verticais:
        for lv in linhas_verticais:
            eixos.axvline(lv, color="red", linestyle=":", alpha=0.7, label="Perturbação")
    eixos.set_ylabel("Erro (°C)")
    _configurar_eixos(eixos, titulo)
    plt.tight_layout()
    if caminho_salvar:
        Path(caminho_salvar).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(caminho_salvar, dpi=150, bbox_inches="tight")
    return fig


def plotar_regime_zoom(
    resultados: Dict[str, np.ndarray],
    t_perturbacao: float,
    margem_antes_s: float = 10.0,
    titulo: str = "Regime permanente — zoom",
    caminho_salvar: Optional[str] = None,
) -> plt.Figure:
    """
    Gráfico ampliado em torno da perturbação: temperatura, erro e potência.
    Eixo X relativo ao instante da perturbação (t = 0 na linha vermelha).
    """
    tempo = resultados["tempo"]
    mask = tempo >= (t_perturbacao - margem_antes_s)
    t_rel = tempo[mask] - t_perturbacao
    setpoint = resultados["setpoint"][mask]
    temperatura = resultados["temperatura"][mask]
    erro = resultados["erro"][mask]
    potencia = resultados.get("potencia_norm")
    potencia_zoom = potencia[mask] * 100 if potencia is not None else None

    fig, eixos = plt.subplots(3, 1, sharex=True, figsize=(10, 8))
    eixos[0].plot(t_rel, setpoint, "--", color="C1", label="Setpoint (°C)")
    eixos[0].plot(t_rel, temperatura, color="C0", label="Temperatura saída (°C)")
    eixos[0].axvline(0, color="red", linestyle=":", alpha=0.7)
    eixos[0].set_ylabel("Temperatura (°C)")
    y_min = min(setpoint.min(), temperatura.min()) - 0.5
    y_max = max(setpoint.max(), temperatura.max()) + 0.5
    eixos[0].set_ylim(y_min, y_max)
    _configurar_eixos(eixos[0], "Temperatura (zoom)")

    eixos[1].plot(t_rel, erro, color="C4", label="Erro (°C)")
    eixos[1].axhline(0, color="gray", linestyle="--")
    eixos[1].axvline(0, color="red", linestyle=":", alpha=0.7)
    eixos[1].set_ylabel("Erro (°C)")
    _configurar_eixos(eixos[1], "Erro (zoom)")

    if potencia_zoom is not None:
        eixos[2].plot(t_rel, potencia_zoom, color="C2", label="Potência (%)")
        eixos[2].axvline(0, color="red", linestyle=":", alpha=0.7, label="Perturbação")
        eixos[2].set_ylabel("Potência (%)")
        _configurar_eixos(eixos[2], "Potência (zoom)", rotulo_x="Tempo relativo à perturbação (s)")
    else:
        eixos[2].set_visible(False)

    fig.suptitle(titulo, fontsize=12)
    plt.tight_layout()
    if caminho_salvar:
        Path(caminho_salvar).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(caminho_salvar, dpi=150, bbox_inches="tight")
    return fig


class Plotador:
    """
    Encapsula a geração de gráficos a partir dos resultados do AmbienteSimulacao.
    Os resultados são passados como dicionário com chaves: tempo, setpoint, temperatura, etc.
    """

    def __init__(self, resultados: Dict[str, np.ndarray]):
        self.resultados = resultados

    def plotar_tudo(
        self,
        titulo: str = "Malha PID - Chuveiro",
        caminho_base: Optional[str] = None,
        mostrar_resistencia: bool = True,
    ) -> list:
        """
        Gera todos os gráficos (resposta e erro).
        Se caminho_base for informado, salva como caminho_base_resposta.png e caminho_base_erro.png.
        Retorna a lista de figuras matplotlib.
        """
        tempo = self.resultados["tempo"]
        setpoint = self.resultados["setpoint"]
        temperatura = self.resultados["temperatura"]
        potencia_norm = self.resultados.get("potencia_norm")
        resistencia_ohm = (
            self.resultados.get("resistencia_ohm") if mostrar_resistencia else None
        )
        erro = self.resultados.get("erro")

        figuras = []
        caminho_resposta = f"{caminho_base}_resposta.png" if caminho_base else None
        figuras.append(
            plotar_resposta(
                tempo,
                setpoint,
                temperatura,
                potencia_norm=potencia_norm,
                resistencia_ohm=resistencia_ohm,
                titulo=titulo,
                caminho_salvar=caminho_resposta,
            )
        )
        if erro is not None:
            caminho_erro = f"{caminho_base}_erro.png" if caminho_base else None
            figuras.append(plotar_erro(tempo, erro, caminho_salvar=caminho_erro))
        return figuras

    def mostrar(self) -> None:
        """
        Exibe as figuras na tela (requer backend interativo, ex.: matplotlib.use('QtAgg')).
        Alternativa: usar matplotlib.pyplot.show() após plotar_tudo().
        """
        plt.show()
