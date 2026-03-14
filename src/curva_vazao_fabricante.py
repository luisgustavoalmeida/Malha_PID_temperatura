"""
Curva característica Vazão Total × Pressão de Entrada do fabricante.

Baseado no gráfico do fabricante: eixo X = Pressão de Entrada dinâmica [m.c.a.],
eixo Y = Vazão Total [L/min]. Permite obter a vazão de saída do chuveiro em função
da pressão da rede hidráulica.

Referência: curva fornecida pelo fabricante (Lorenzetti Advanced Eletrônica Blindada).
"""

from typing import Optional, List, Tuple
import numpy as np


# Pontos da curva (pressão m.c.a., vazão L/min) extraídos do gráfico do fabricante
# Trecho inicial: subida acentuada; 5–9 m.c.a.: patamar; 9–40 m.c.a.: subida gradual
CURVA_VAZAO_PRESSAO_FABRICANTE: List[Tuple[float, float]] = [
    (1.0, 3.2),
    (5.0, 6.9),
    (6.0, 7.0),
    (8.0, 6.8),
    (9.0, 6.9),
    (10.0, 7.2),
    (15.0, 8.0),
    (20.0, 8.7),
    (25.0, 9.2),
    (30.0, 9.5),
    (35.0, 9.7),
    (40.0, 9.9),
]

# Valores separados para interpolação
_PRESSOES_MCA = np.array([p[0] for p in CURVA_VAZAO_PRESSAO_FABRICANTE])
_VAZOES_LMIN = np.array([p[1] for p in CURVA_VAZAO_PRESSAO_FABRICANTE])

# Limites da curva (úteis para limitar entradas)
PRESSAO_MINIMA_MCA = float(_PRESSOES_MCA.min())
PRESSAO_MAXIMA_MCA = float(_PRESSOES_MCA.max())
VAZAO_MINIMA_CURVA_LMIN = float(_VAZOES_LMIN.min())
VAZAO_MAXIMA_CURVA_LMIN = float(_VAZOES_LMIN.max())


def vazao_por_pressao(
    pressao_entrada_mca: float,
    extrapolar: bool = False,
) -> float:
    """
    Retorna a vazão total de saída do chuveiro [L/min] para uma dada pressão
    de entrada (dinâmica) em metros de coluna d'água [m.c.a.].

    Utiliza interpolação linear entre os pontos da curva do fabricante.
    Abaixo da pressão mínima da curva retorna a vazão mínima; acima da máxima,
    retorna a vazão máxima (a menos que extrapolar=True).

    Argumentos:
        pressao_entrada_mca: pressão de entrada da água [m.c.a.]
        extrapolar: se True, permite extrapolar fora do range da curva (linear)

    Retorna:
        Vazão total [L/min].
    """
    if not extrapolar:
        pressao_entrada_mca = np.clip(
            pressao_entrada_mca, PRESSAO_MINIMA_MCA, PRESSAO_MAXIMA_MCA
        )
    return float(np.interp(pressao_entrada_mca, _PRESSOES_MCA, _VAZOES_LMIN))


def pressao_por_vazao(
    vazao_lmin: float,
    extrapolar: bool = False,
) -> float:
    """
    Retorna a pressão de entrada [m.c.a.] que produz a vazão dada [L/min],
    segundo a curva do fabricante (inversa da curva vazão × pressão).

    Útil para estimar pressão a partir de uma vazão desejada.
    """
    if not extrapolar:
        vazao_lmin = np.clip(
            vazao_lmin, VAZAO_MINIMA_CURVA_LMIN, VAZAO_MAXIMA_CURVA_LMIN
        )
    return float(np.interp(vazao_lmin, _VAZOES_LMIN, _PRESSOES_MCA))


def obter_pontos_curva() -> tuple[np.ndarray, np.ndarray]:
    """
    Retorna os arrays (pressões [m.c.a.], vazões [L/min]) da curva do fabricante,
    para plotagem ou análise.
    """
    return _PRESSOES_MCA.copy(), _VAZOES_LMIN.copy()
