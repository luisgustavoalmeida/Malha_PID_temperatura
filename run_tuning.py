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

from ambientes import AmbienteRespostaDegrau, AmbienteTuningML
from ambientes.sintonia_ml import criterio_iae
from src import AmbienteSimulacao, ParamsChuveiro, ParamsPID


def main():
    """
    Executa ajuste da malha PID: simula resposta ao degrau, faz busca em grade (Kp, Ki, Kd)
    para minimizar o critério IAE e gera gráficos da resposta inicial e do PID otimizado.
    """
    params_chuveiro = ParamsChuveiro(
        temperatura_inicial_agua=20.0,   # °C — água na entrada
        temperatura_desejada=38.0,       # °C — setpoint alvo
        temperatura_ambiente=25.0,       # °C — ambiente (perdas)
        perda_meio=1.0,                  # W/K — perdas térmicas
        eficiencia_chuveiro=0.95,        # 0–1 — eficiência
        potencia_minima=0.0,             # W
        potencia_maxima=6000.0,          # W — nominal
        modo_controle_potencia="degrau", # quantização de potência
        numero_passos_potencia=100,      # níveis 0..100
        vazao_minima=2.5,                # L/min
        vazao_maxima=10.0,               # L/min
        volume_canal=0.7,                # L — atraso de transporte
    )

    # ---- Ambiente de resposta ao degrau (teste de malha) ----
    ambiente_degrau = AmbienteRespostaDegrau(
        params_chuveiro=params_chuveiro,
        params_pid=ParamsPID(
            Kp=0.11, Ki=0.008, Kd=0.60,  # ganhos PID iniciais para avaliação
            saida_minima=0.0, saida_maxima=1.0,
        ),
        t_degrau_s=5.0,       # s — instante do degrau de setpoint
        duracao_s=120.0,      # s — duração da simulação
        vazao_lmin=2.5,       # L/min — vazão fixa
    )
    print("Simulando resposta ao degrau inicial...")
    p = ambiente_degrau.params_pid
    titulo_inicial = f"Resposta ao degrau - PID inicial (Kp={p.Kp:.3g}, Ki={p.Ki:.3g}, Kd={p.Kd:.3g})"
    resultados, plotador = ambiente_degrau.executar_e_plotar(
        caminho_base="saida_tuning/resposta_degrau",
        titulo=titulo_inicial,
    )
    plt.show()

    # ---- Busca em grade (grid search) de Kp, Ki, Kd — minimiza IAE ----
    ambiente_ml = AmbienteTuningML(
        params_chuveiro=params_chuveiro,
        ambiente_degrau=ambiente_degrau,  # cenário de teste compartilhado
        criterio=criterio_iae,            # Integral do |erro| — quanto menor, melhor
    )
    lista_Kp = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16]
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
