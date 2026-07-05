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
from src.graficos import Plotador


def main():
    """
    Configura parâmetros do chuveiro e do PID, executa a simulação da malha fechada
    (resposta ao degrau) e gera gráficos na pasta saida_simulacao.
    """
    # ---- Parâmetros do chuveiro (modelo físico da planta) ----
    params_chuveiro = ParamsChuveiro(
        temperatura_inicial_agua=20.0,   # °C — água na entrada (também setpoint antes do degrau)
        temperatura_desejada=40.0,       # °C — alvo da malha após o degrau
        temperatura_ambiente=25.0,       # °C — ambiente para cálculo de perdas térmicas
        vazao_minima=2.0,                # L/min — limite inferior de vazão no modelo
    )

    # ---- Parâmetros do PID (ganhos da malha de controle) ----
    params_pid = ParamsPID(
        Kp=0.04,           # ganho proporcional — resposta ao erro instantâneo
        Ki=0.0013,          # ganho integral — elimina erro em regime
        Kd=0.375,            # ganho derivativo — amortecimento (derivada da medida, −Kd·dPV/dt)
        saida_minima=0.0,   # saída mínima normalizada (0 = potência mínima)
        saida_maxima=1.0,   # saída máxima normalizada (1 = potência máxima)
    )

    # ---- Potenciômetro eletrônico (mapeamento saída PID → resistência para ESP32) ----
    potenciometro = MapeamentoPotenciometro(
        resistencia_total_ohms=200_000.0,  # Ω — resistência total do potenciômetro
        curva="linear",                      # "linear" ou "log"
    )

    # ---- Cenário: resposta ao degrau de setpoint ----
    t_degrau_s = 5.0  # s — instante em que o setpoint salta para temperatura_desejada

    def setpoint_degrau(tempo):
        return (
            params_chuveiro.temperatura_desejada
            if tempo >= t_degrau_s
            else params_chuveiro.temperatura_inicial_agua
        )

    # ---- Configuração temporal e do sensor (alinhado ao firmware ESP32) ----
    config = ConfiguracaoSimulacao(
        duracao_s=500.0,                    # s — tempo total da simulação
        dt_s=0.1,                           # s — passo de integração da planta
        vazao_lmin=1.0,                     # L/min — vazão fixa durante a simulação
        setpoint_funcao=setpoint_degrau,    # lei do setpoint em função do tempo
        tempo_aquisicao_sensor_s=0.38,      # s — período entre leituras do sensor (380 ms)
        tempo_calculo_pid_s=0.38,           # s — período entre cálculos do PID (380 ms)
        sensor_resolucao_c=0.125,           # °C — quantização: round(temp/0.125)*0.125 (11 bits)
        sensor_janela_media_movel=3,        # amostras — média móvel sobre leituras quantizadas
        setpoint_atraso_aplicacao_s=1.5,    # s — atraso encoder→malha (ESP32: ALVO_TEMP_PAUSA_MS)
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
