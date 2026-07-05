"""
Ajuste robusto da malha PID: encontra os melhores (Kp, Ki, Kd) que funcionam bem
independente das condições de entrada e saída.

Varre temperaturas (inicial, desejada, ambiente), vazão e ganhos PID usando
ranges configuráveis (início, fim, passo) para cada variável.

Para focar em atingir a temperatura desejada mais rápido e estável:
  - Use criterio_rapido_estavel: ITAE + penalidade de overshoot.
  - ITAE favorece resposta rápida; overshoot favorece estabilidade (menos ultrapassagem).

Para focar em regime permanente sem erro e resposta estável (recomendado para chuveiro):
  - Priorize o ranking de estavel_sem_erro; entre os top 10, escolha o menor settling_time.
  - Pesos atuais: erro_regime=10, oscilacao=8, overshoot=8, undershoot=2, banda ±1%.
  - agregar="max" garante estabilidade no pior cenário (vazão/temperatura).

Uso:
  python run_tuning_robusto.py

Ajuste os ranges em RangesTuningRobusto abaixo (inicio, fim, passo de cada variável).
Para acelerar, o tuning usa multiprocessing (vários processos em paralelo).
Use num_workers=1 em tuner.executar() para desativar o paralelismo.
"""

import sys
from functools import partial
from pathlib import Path


def _num_workers_padrao():
    """
    None = usa todos os núcleos (padrão, ~6 min no tuning completo).
    1 = série — só com --serie ou quando o debugger (debugpy) está ativo.
    """
    if "debugpy" in sys.modules:
        return 1
    if "--serie" in sys.argv:
        return 1
    if "--paralelo" in sys.argv:
        return None
    return None


def _modo_teste() -> bool:
    return "--teste" in sys.argv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ambientes.sintonia_ml import (
    criterio_estavel_sem_erro,
    criterio_rapido_estavel,
)
from ambientes.sintonia_robusta import (
    RangesTuningRobusto,
    RangeVar,
    TuningRobusto,
)
from src import ParamsChuveiro


def main():
    """
    Executa o ajuste robusto da malha PID: varre condições de operação e ganhos (Kp, Ki, Kd),
    avalia múltiplos critérios (IAE, ITAE, overshoot, etc.) e salva os top 10 por categoria.
    """
    # ---- Parâmetros fixos do chuveiro (não variados no tuning; só condições e ganhos variam) ----
    params_base = ParamsChuveiro(

    )

    # ---- Ranges de varredura (inicio, fim, passo) ----
    # inicio == fim → valor fixo; passo define a grade de busca

    ranges = RangesTuningRobusto(
        temperatura_inicial_agua=RangeVar(inicio=25.0, fim=25.0, passo=4.0),  # °C entrada
        temperatura_desejada=RangeVar(inicio=40.0, fim=40.0, passo=1.0),    # °C setpoint
        temperatura_ambiente=RangeVar(inicio=26.0, fim=26.0, passo=10),     # °C ambiente
        vazao_lmin=RangeVar(inicio=2.0, fim=3.5, passo=1.5),                # L/min
        Kp=RangeVar(inicio=0.000, fim=0.05, passo=0.005),                   # ganho P
        Ki=RangeVar(inicio=0.000, fim=0.002, passo=0.00005),                 # ganho I
        Kd=RangeVar(inicio=0.000, fim=0.50, passo=0.005),                   # ganho D
    )

    # ---- Critérios: avaliar em uma única passada e guardar top 10 de cada categoria ----
    # Integrais: iae, itae, ise, itse
    # Resposta ao degrau: overshoot, undershoot, settling_time, rise_time, peak_time
    # Regime permanente: erro_regime, oscilacao_regime
    # Compostos: rapido_estavel (ITAE + overshoot), estavel_sem_erro (erro nulo + estabilidade)
    criterios = {
        # Integrais do erro (quanto menor, melhor)
        # "iae": criterio_iae,       # Integral do |erro| — penaliza erro total
        # "itae": criterio_itae,     # Integral de tempo×|erro| — prioriza resposta rápida
        # "ise": criterio_ise,       # Integral do erro² — penaliza mais erros grandes
        # "itse": criterio_itse,     # Integral de tempo×erro² — erros grandes e tardios
        # Resposta ao degrau (quanto menor, melhor)
        # "overshoot": criterio_overshoot,     # % que a saída ultrapassou o setpoint
        # "undershoot": criterio_undershoot,   # % que a saída ficou abaixo do inicial
        # "settling_time": criterio_settling_time,  # [s] até entrar na faixa ±2% do setpoint
        # "rise_time": criterio_rise_time,    # [s] de 10% a 90% do valor final
        # "peak_time": criterio_peak_time,    # [s] instante do primeiro pico (máximo)
        # Regime permanente (quanto menor, melhor)
        # "erro_regime": partial(criterio_erro_regime, fracao_regime=0.4),
        # "oscilacao_regime": partial(criterio_oscilacao_regime, fracao_regime=0.4),
        # Compostos
        "rapido_estavel": partial(criterio_rapido_estavel, peso_overshoot=0.1),
        "estavel_sem_erro": partial(
            criterio_estavel_sem_erro,
            fracao_regime=0.4,              # fração final da simulação usada como regime
            peso_erro_regime=10.0,          # peso do erro médio em regime
            peso_oscilacao=9.0,             # peso da oscilação em regime
            peso_overshoot=7.0,            # peso da ultrapassagem do setpoint
            peso_undershoot=7.0,           # peso de ficar abaixo do setpoint
            penalidade_sem_acomodacao=100_000.0,  # penalidade se não estabilizar
            banda_pct=1.0,                  # % — faixa ± em torno do setpoint para regime
        ),
    }

    # ---- Configuração do tuning robusto ----
    tuner = TuningRobusto(
        params_chuveiro_base=params_base,   # parâmetros fixos da planta
        ranges=ranges,                      # grades de condições e ganhos PID
        duracao_s=200.0,                    # s — duração de cada simulação
        dt_s=0.1,                           # s — passo de integração da planta
        t_degrau_s=3.0,                     # s — instante do degrau de setpoint
        tempo_aquisicao_sensor_s=0.38,      # s — período de leitura do sensor (380 ms)
        tempo_calculo_pid_s=0.38,           # s — período de cálculo do PID (380 ms)
        sensor_resolucao_c=0.125,           # °C — quantização 11 bits do sensor
        sensor_janela_media_movel=3,        # amostras — média móvel do sensor
        setpoint_atraso_aplicacao_s=1.5,    # s — atraso encoder→malha (ALVO_TEMP_PAUSA_MS)
        criterios=criterios,                # critérios avaliados em paralelo
        agregar="max",                      # "max" = pior cenário; "media" = média
    )

    n_cond = len(ranges.gerar_condicoes())
    n_pid = len(ranges.gerar_pid())
    print(f"Condições de operação: {n_cond}", flush=True)
    print(f"Combinações PID: {n_pid}", flush=True)
    print(f"Total de simulações: {n_cond * n_pid}", flush=True)
    # num_workers: None = todos os núcleos (terminal); 1 = série (Play/Debug no Windows)
    num_workers = _num_workers_padrao()
    if num_workers == 1:
        print(
            "Execução em série (debugger ativo ou --serie). "
            "Use Play > Terminal Dedicado ou --paralelo para ~6 min.",
            flush=True,
        )
        print(f"Tempo estimado: ~{max(1, n_pid * 0.15 / 60):.0f} min", flush=True)
    else:
        print(
            "Paralelo ativo: a barra pode ficar em 0% por ~1 min "
            "enquanto os workers iniciam (normal no Windows).",
            flush=True,
        )
    print("Executando tuning robusto...", flush=True)

    rankings_por_categoria = tuner.executar(mostrar_progresso=True, num_workers=num_workers)

    TOP_N = 10
    for nome_cat, ranking in rankings_por_categoria.items():
        print(f"\n--- Categoria: {nome_cat} (top {TOP_N}) ---")
        for (Kp, Ki, Kd), valor in ranking[:TOP_N]:
            print(f"  Kp={Kp:.3g} Ki={Ki:.3g} Kd={Kd:.3g}  -> {valor:.2f}")
        (Kp_m, Ki_m, Kd_m), v_m = ranking[0]
        print(f"  Melhor: Kp={Kp_m}, Ki={Ki_m}, Kd={Kd_m}  -> {v_m:.2f}")

    # Salvar os 10 melhores de cada categoria em arquivo
    pasta = Path("saida_tuning")
    pasta.mkdir(exist_ok=True)
    arquivo = pasta / "tuning_robusto_resultado.txt"
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write("Tuning robusto - top 10 por categoria\n")
        f.write("=" * 50 + "\n")
        f.write(f"Condições: {n_cond}  |  Combinações PID: {n_pid}\n")
        f.write(f"Agregação: {tuner.agregar}\n\n")
        for nome_cat, ranking in rankings_por_categoria.items():
            f.write(f"--- {nome_cat} (top {TOP_N}) ---\n")
            for (Kp, Ki, Kd), v in ranking[:TOP_N]:
                f.write(f"  Kp={Kp} Ki={Ki} Kd={Kd}  -> {v:.4f}\n")
            f.write("\n")
    print(f"\nResultado salvo em {arquivo}")


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()

