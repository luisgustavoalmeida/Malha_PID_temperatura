"""
Script de ajuste da malha PID: resposta ao degrau + busca em grade (grid search).

Uso:
  python run_tuning.py

Gera gráficos da resposta e varre Kp, Ki, Kd para minimizar o critério IAE.
Recomenda-se ativar o ambiente virtual antes: .venv\\Scripts\\activate
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt

from environments import AmbienteRespostaDegrau, AmbienteTuningML
from environments.ml_tuning import criterio_iae
from src import AmbienteSimulacao, ParamsChuveiro, ParamsPID


def main():
    params_chuveiro = ParamsChuveiro(
        temperatura_inicial_agua=20.0,
        temperatura_desejada=38.0,
        temperatura_ambiente=25.0,
        perda_meio=1.0,
        eficiencia_chuveiro=0.95,  # Etiqueta: 95%
        potencia_minima=0.0,
        potencia_maxima=6000.0,  # 6000W nominal
        vazao_minima=2.5,
        vazao_maxima=10.0,
        volume_canal=0.7,  # [L] volume do canal aquecedor → saída
    )

    # ---- Ambiente de resposta ao degrau ----
    ambiente_degrau = AmbienteRespostaDegrau(
        params_chuveiro=params_chuveiro,
        params_pid=ParamsPID(Kp=0.11, Ki=0.008, Kd=0.60, saida_minima=0.0, saida_maxima=1.0),
        t_degrau_s=5.0,
        duracao_s=120.0,
        vazao_lmin=2.5,
    )
    print("Simulando resposta ao degrau inicial...")
    p = ambiente_degrau.params_pid
    titulo_inicial = f"Resposta ao degrau - PID inicial (Kp={p.Kp:.3g}, Ki={p.Ki:.3g}, Kd={p.Kd:.3g})"
    resultados, plotador = ambiente_degrau.executar_e_plotar(
        caminho_base="saida_tuning/resposta_degrau",
        titulo=titulo_inicial,
    )
    plt.show()

    # ---- Busca em grade (grid search) ----
    ambiente_ml = AmbienteTuningML(
        params_chuveiro=params_chuveiro,
        ambiente_degrau=ambiente_degrau,
        criterio=criterio_iae,
    )
    lista_Kp = [ 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16]
    lista_Ki = [0.000, 0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.010, 0.011]
    lista_Kd = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    ranking = ambiente_ml.busca_grade(lista_Kp, lista_Ki, lista_Kd, mostrar_progresso=True)
    print("Top 5 conjuntos (menor IAE):")
    for (Kp, Ki, Kd), valor in ranking[:5]:
        print(f"  Kp={Kp:.3f} Ki={Ki:.3f} Kd={Kd:.3f}  IAE={valor:.3f}")

    # ---- Melhor PID: rodar e plotar ----
    (Kp_melhor, Ki_melhor, Kd_melhor), _ = ranking[0]
    ambiente_degrau.params_pid = ParamsPID(
        Kp=Kp_melhor, Ki=Ki_melhor, Kd=Kd_melhor,
        saida_minima=0.0, saida_maxima=1.0,
    )
    ambiente_degrau.simulacao = AmbienteSimulacao(
        params_chuveiro=ambiente_degrau.params_chuveiro,
        params_pid=ambiente_degrau.params_pid,
    )
    print("Gerando gráficos do PID otimizado...")
    resultados2, plotador2 = ambiente_degrau.executar_e_plotar(
        caminho_base="saida_tuning/resposta_degrau_otimizado",
        titulo=f"Resposta ao degrau - PID otimizado (Kp={Kp_melhor:.3g}, Ki={Ki_melhor:.3g}, Kd={Kd_melhor:.3g})",
    )
    plt.show()
    print("Ajuste concluído. Gráficos em saida_tuning/")


if __name__ == "__main__":
    main()
