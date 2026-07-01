"""
Ajuste robusto da malha PID: encontra os melhores (Kp, Ki, Kd) que funcionam bem
independente das condições de entrada e saída.

Varre temperaturas (inicial, desejada, ambiente), vazão e ganhos PID usando
ranges configuráveis (início, fim, passo) para cada variável.

Para focar em atingir a temperatura desejada mais rápido e estável:
  - Use criterio_rapido_estavel: ITAE + penalidade de overshoot.
  - ITAE favorece resposta rápida; overshoot favorece estabilidade (menos ultrapassagem).

Para focar em regime permanente sem erro e resposta estável:
  - Use criterio_estavel_sem_erro: erro/oscilação na fase final + overshoot/undershoot.
  - Ajuste peso_erro_regime (erro nulo) e peso_oscilacao / peso_overshoot (estabilidade).

Uso:
  python run_tuning_robusto.py

Ajuste os ranges em RangesTuningRobusto abaixo (inicio, fim, passo de cada variável).
Para acelerar, o tuning usa multiprocessing (vários processos em paralelo).
Use num_workers=1 em tuner.executar() para desativar o paralelismo.
"""

import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ambientes.sintonia_ml import (
    criterio_erro_regime,
    criterio_estavel_sem_erro,
    criterio_iae,
    criterio_ise,
    criterio_itae,
    criterio_itse,
    criterio_oscilacao_regime,
    criterio_overshoot,
    criterio_peak_time,
    criterio_rapido_estavel,
    criterio_rise_time,
    criterio_settling_time,
    criterio_undershoot,
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
    # ---- Parâmetros fixos do chuveiro (não variados no tuning) ----
    params_base = ParamsChuveiro(
        perda_meio=0.2,
        eficiencia_chuveiro=0.95,
        potencia_minima=0.0,
        potencia_maxima=6000.0,
        vazao_minima=2.5,
        vazao_maxima=10.0,
        volume_canal=0.7,
    )

    # ---- Ranges: início, fim e passo de cada variável ----
    # Condições de operação (serão variadas)
    ranges = RangesTuningRobusto(
        temperatura_inicial_agua=RangeVar(inicio=23.0, fim=23.0, passo=4.0),
        temperatura_desejada=RangeVar(inicio=38.0, fim=38.0, passo=1.0),
        temperatura_ambiente=RangeVar(inicio=26.0, fim=26.0, passo=10),
        vazao_lmin=RangeVar(inicio=2.5, fim=3.5, passo=1.0),
        # Ganhos PID a buscar
        Kp=RangeVar(inicio=0.000, fim=0.06, passo=0.002),
        Ki=RangeVar(inicio=0.000, fim=0.003, passo=0.0002),
        Kd=RangeVar(inicio=0.000, fim=0.50, passo=0.002),
    )

    # ---- Critérios: avaliar em uma única passada e guardar top 10 de cada categoria ----
    # Integrais: iae, itae, ise, itse
    # Resposta ao degrau: overshoot, undershoot, settling_time, rise_time, peak_time
    # Regime permanente: erro_regime, oscilacao_regime
    # Compostos: rapido_estavel (ITAE + overshoot), estavel_sem_erro (erro nulo + estabilidade)
    criterios = {
        # Integrais do erro (quanto menor, melhor)
        "iae": criterio_iae,       # Integral do |erro| — penaliza erro total
        "itae": criterio_itae,     # Integral de tempo×|erro| — prioriza resposta rápida
        "ise": criterio_ise,       # Integral do erro² — penaliza mais erros grandes
        "itse": criterio_itse,     # Integral de tempo×erro² — erros grandes e tardios
        # Resposta ao degrau (quanto menor, melhor)
        "overshoot": criterio_overshoot,     # % que a saída ultrapassou o setpoint
        "undershoot": criterio_undershoot,   # % que a saída ficou abaixo do inicial
        "settling_time": criterio_settling_time,  # [s] até entrar na faixa ±2% do setpoint
        "rise_time": criterio_rise_time,    # [s] de 10% a 90% do valor final
        "peak_time": criterio_peak_time,    # [s] instante do primeiro pico (máximo)
        # Regime permanente (quanto menor, melhor)
        "erro_regime": partial(criterio_erro_regime, fracao_regime=0.4),
        "oscilacao_regime": partial(criterio_oscilacao_regime, fracao_regime=0.4),
        # Compostos
        "rapido_estavel": partial(criterio_rapido_estavel, peso_overshoot=0.1),
        "estavel_sem_erro": partial(
            criterio_estavel_sem_erro,
            fracao_regime=0.4,
            peso_erro_regime=10.0,
            peso_oscilacao=3.0,
            peso_overshoot=1.0,
            peso_undershoot=0.5,
        ),
    }

    # ---- Tuning robusto (uma passada, rankings por categoria) ----
    tuner = TuningRobusto(
        params_chuveiro_base=params_base,
        ranges=ranges,
        duracao_s=250.0,
        dt_s=0.1,
        t_degrau_s=3.0,
        criterios=criterios,
        agregar="max",  # "media" ou "max" (pior caso)
    )

    n_cond = len(ranges.gerar_condicoes())
    n_pid = len(ranges.gerar_pid())
    print(f"Condições de operação: {n_cond}")
    print(f"Combinações PID: {n_pid}")
    print(f"Total de simulações: {n_cond * n_pid}")
    # num_workers: None = paralelo (cpu_count-1); 1 = só um processo (sem paralelismo)
    num_workers = None
    print("Executando tuning robusto...")

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
    main()

