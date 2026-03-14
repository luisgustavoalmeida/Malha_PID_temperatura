"""
Script principal: simula a malha PID do chuveiro e gera gráficos.

Uso:
  python run_simulation.py

Ajuste os parâmetros do chuveiro em ParamsChuveiro e do PID em ParamsPID abaixo.
Recomenda-se ativar o ambiente virtual antes: .venv\\Scripts\\activate
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt

from src import (
    AmbienteSimulacao,
    ConfiguracaoSimulacao,
    MapeamentoPotenciometro,
    ParamsChuveiro,
    ParamsPID,
)
from src.plotter import Plotador


def main():
    # ---- Parâmetros do chuveiro (Lorenzetti 220V 6000W – curva do fabricante) ----
    params_chuveiro = ParamsChuveiro(
        temperatura_inicial_agua=20.0,
        temperatura_desejada=38.0,
        temperatura_ambiente=10.0,
        perda_meio=0.2,
        eficiencia_chuveiro=0.95,   # Etiqueta: 95%
        potencia_minima=0.0,
        potencia_maxima=6000.0,    #6000W nominal
        vazao_minima=2.5,
        vazao_maxima=10.0,
        volume_canal=0.7,  # [L] volume do canal aquecedor → saída
    )

    # ---- Parâmetros do PID (ajustar para tuning) ----
    params_pid = ParamsPID(
        Kp=0.032,
        Ki=0.002,
        Kd=0.015,
        saida_minima=0.0,
        saida_maxima=1.0,
    )

    # ---- Potenciômetro 50 kΩ (para ESP32) ----
    potenciometro = MapeamentoPotenciometro(
        resistencia_total_ohms=50_000.0, curva="linear"
    )

    # ---- Configuração da simulação: resposta ao degrau ----
    # O setpoint usa temperatura_inicial_agua até t_degrau_s e depois temperatura_desejada
    t_degrau_s = 5.0  # instante do degrau [s]

    def setpoint_degrau(tempo):
        return (
            params_chuveiro.temperatura_desejada
            if tempo >= t_degrau_s
            else params_chuveiro.temperatura_inicial_agua
        )

    config = ConfiguracaoSimulacao(
        duracao_s=350.0,
        dt_s=0.1,
        vazao_lmin=3,
        setpoint_funcao=setpoint_degrau,
    )

    # ---- Executar simulação e plotar ----
    ambiente = AmbienteSimulacao(
        params_chuveiro=params_chuveiro,
        params_pid=params_pid,
        mapeamento_potenciometro=potenciometro,
    )
    ambiente.executar(config)
    resultados = ambiente.obter_resultados()

    plotador = Plotador(resultados)
    # plotador.plotar_tudo(
    #     titulo="Malha PID - Temperatura do Chuveiro (resposta ao degrau)",
    #     caminho_base="saida_simulacao",
    #     mostrar_resistencia=False,
    # )

    # Salvar gráficos na pasta saida_simulacao
    pasta_saida = Path("saida_simulacao")
    pasta_saida.mkdir(exist_ok=True)
    plotador.plotar_tudo(
        titulo=f"Malha PID - Temperatura do Chuveiro (Kp={params_pid.Kp:.3g}, Ki={params_pid.Ki:.3g}, Kd={params_pid.Kd:.3g})",
        caminho_base=str(pasta_saida / "malha_pid"),
        mostrar_resistencia=False,
    )
    plt.show()
    print("Simulação concluída. Gráficos em saida_simulacao/")


if __name__ == "__main__":
    main()
