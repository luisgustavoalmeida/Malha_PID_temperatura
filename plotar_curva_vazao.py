"""
Plota a curva característica Vazão × Pressão de Entrada do fabricante.

Uso:
  python plotar_curva_vazao.py

Gera o gráfico da curva de vazão disponibilizada pelo fabricante e salva em
saida_simulacao/curva_vazao_fabricante.png.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import obter_pontos_curva, vazao_por_pressao
import numpy as np
import matplotlib.pyplot as plt


def main():
    pressoes, vazoes = obter_pontos_curva()
    # Curva suave para plot (mais pontos por interpolação)
    pressoes_fino = np.linspace(pressoes.min(), pressoes.max(), 200)
    vazoes_fino = np.array([vazao_por_pressao(p) for p in pressoes_fino])

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(pressoes_fino, vazoes_fino, "b-", label="Curva do fabricante (interpolada)")
    ax.plot(pressoes, vazoes, "ko", markersize=6, label="Pontos da curva")
    ax.set_xlabel("Pressão de Entrada - dinâmica (m.c.a.)")
    ax.set_ylabel("Vazão Total (L/min)")
    ax.set_title("Curva característica Vazão Total × Pressão de Entrada (fabricante)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    ax.set_xlim(0, 42)
    ax.set_ylim(0, 13)
    plt.tight_layout()

    pasta = Path("saida_simulacao")
    pasta.mkdir(exist_ok=True)
    caminho = pasta / "curva_vazao_fabricante.png"
    plt.savefig(caminho, dpi=150, bbox_inches="tight")
    print(f"Curva salva em {caminho}")
    plt.show()


if __name__ == "__main__":
    main()
