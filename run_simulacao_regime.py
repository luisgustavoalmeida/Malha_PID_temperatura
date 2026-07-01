"""
Simulacao em regime permanente: perturbacao pequena apos estabilizacao.

Uma unica malha PID: ganhos de partida ate t_troca_regime, depois ganhos de regime
(mesmo estado integral — troca sem vale na potencia).

Uso:
  python run_simulacao_regime.py
  python run_simulacao_regime.py --tipo sensor
  python run_simulacao_regime.py --t-troca-regime 200 --t-pert 350
  python run_simulacao_regime.py --sem-troca-ganhos   # so params_pid_partida
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt

from ambientes.regime_permanente import AmbienteRegimePermanente
from src import MapeamentoPotenciometro, ParamsChuveiro, ParamsPID

# ---- Ganhos partida (ate t_troca_regime) ----
# ---- Ganhos regime (a partir de t_troca_regime) ----
T_TROCA_REGIME_S = 300.0  # instante [s] da troca de ganhos; None = sem troca
CRITERIO_TROCA_REGIME = "tempo"  # "tempo" | "erro" | "hibrido"


def _formatar_metricas(metricas) -> str:
    t_acom = (
        f"{metricas.t_acomodacao_s:.1f} s"
        if metricas.t_acomodacao_s != float("inf")
        else "nao acomodou"
    )
    return (
        f"  Potencia estavel antes da perturbacao: {metricas.potencia_estavel_w:.0f} W\n"
        f"  Temperatura estavel antes da perturbacao: {metricas.temperatura_estavel_c:.2f} C\n"
        f"  Tempo de acomodacao (|erro| <= banda): {t_acom}\n"
        f"  Erro pico pos-perturbacao: {metricas.erro_pico_c:.3f} C\n"
        f"  ITAE local: {metricas.itae_local:.3f}\n"
        f"  Oscilacao do erro (final): {metricas.oscilacao_erro:.4f} C\n"
        f"  Erro final: {metricas.erro_final_c:.3f} C"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Simulacao regime permanente — um PID, ganhos trocam no instante configurado"
    )
    parser.add_argument(
        "--tipo",
        choices=["setpoint", "sensor", "entrada"],
        default="setpoint",
        help="Tipo de perturbacao apos estabilizacao",
    )
    parser.add_argument("--t-degrau", type=float, default=5.0, help="Degrau de partida [s]")
    parser.add_argument("--t-pert", type=float, default=400.0, help="Perturbacao pequena [s]")
    parser.add_argument("--duracao", type=float, default=1000.0, help="Duracao total [s]")
    parser.add_argument(
        "--t-troca-regime",
        type=float,
        default=T_TROCA_REGIME_S,
        help="Instante [s] para trocar Kp/Ki/Kd para params_pid_regime",
    )
    parser.add_argument(
        "--troca-por",
        choices=["tempo", "erro", "hibrido"],
        default=CRITERIO_TROCA_REGIME,
        help="Criterio da troca de ganhos",
    )
    parser.add_argument(
        "--sem-troca-ganhos",
        action="store_true",
        help="Usa so params_pid_partida (ignora params_pid_regime)",
    )
    args = parser.parse_args()

    t_troca = None if args.sem_troca_ganhos else args.t_troca_regime

    if args.troca_por == "tempo" and t_troca is None and not args.sem_troca_ganhos:
        parser.error("Defina --t-troca-regime ou use --sem-troca-ganhos")

    if t_troca is not None and args.t_pert <= t_troca + 20:
        print(
            f"Aviso: t-pert={args.t_pert}s proximo da troca de ganhos (t={t_troca}s). "
            "Recomendado t-pert > t-troca-regime + 50s."
        )

    params_chuveiro = ParamsChuveiro(
        temperatura_inicial_agua=20.0,
        temperatura_desejada=39.0,
        temperatura_ambiente=20.0,
        perda_meio=0.5,
        eficiencia_chuveiro=0.95,
        potencia_minima=0.0,
        potencia_maxima=6000.0,
        vazao_minima=2.5,
        vazao_maxima=10.0,
        volume_canal=0.7,
    )

    params_pid_partida = ParamsPID(
        Kp=0.025,
        Ki=0.0013,
        Kd=0.01,
        saida_minima=0.0,
        saida_maxima=1.0,
    )

    params_pid_regime = ParamsPID(
        Kp=0.025,
        Ki=0.0013,
        Kd=0.01,
        saida_minima=0.0,
        saida_maxima=1.0,
    )

    potenciometro = MapeamentoPotenciometro(
        resistencia_total_ohms=200_000.0, curva="linear"
    )

    pid_regime = None if args.sem_troca_ganhos else params_pid_regime

    ambiente = AmbienteRegimePermanente(
        tipo_perturbacao=args.tipo,  # type: ignore[arg-type]
        t_degrau_s=args.t_degrau,
        t_perturbacao_s=args.t_pert,
        delta_setpoint_c=-0.3,
        bias_sensor_c=-0.3,
        duracao_bias_s=5.0,
        delta_entrada_c=-1.0,
        duracao_entrada_s=8.0,
        params_chuveiro=params_chuveiro,
        params_pid=params_pid_partida,
        params_pid_regime=pid_regime,
        limiar_erro_partida=2.0,
        limiar_erro_regime=0.8,
        t_troca_regime_s=t_troca,
        criterio_troca_regime=args.troca_por,  # type: ignore[arg-type]
        mapeamento_potenciometro=potenciometro,
        duracao_s=args.duracao,
        dt_s=0.1,
        vazao_lmin=3.0,
        banda_acomodacao_c=0.2,
    )

    pasta_saida = Path("saida_simulacao")
    pasta_saida.mkdir(exist_ok=True)
    caminho_base = str(pasta_saida / f"regime_{args.tipo}")

    if pid_regime is None:
        modo_txt = "ganhos fixos (partida)"
    elif t_troca is not None:
        modo_txt = f"ganhos regime em t={t_troca:.0f}s ({args.troca_por})"
    else:
        modo_txt = f"troca por {args.troca_por}"

    titulo = (
        f"Regime permanente — {args.tipo} | {modo_txt} | "
        f"degrau t={args.t_degrau:.0f}s | perturbacao t={args.t_pert:.0f}s"
    )

    resultados, metricas, _ = ambiente.executar_e_plotar(
        caminho_base=caminho_base,
        titulo=titulo,
    )

    print(f"\n=== Simulacao regime permanente ({args.tipo}) ===")
    print(f"Malha: unica PID | {modo_txt}")
    print(
        f"  Partida (t < troca): Kp={params_pid_partida.Kp}, "
        f"Ki={params_pid_partida.Ki}, Kd={params_pid_partida.Kd}"
    )
    if pid_regime:
        print(
            f"  Regime (apos troca): Kp={params_pid_regime.Kp}, "
            f"Ki={params_pid_regime.Ki}, Kd={params_pid_regime.Kd}"
        )
    print(f"\nMetricas pos-perturbacao (banda +/-{ambiente.banda_acomodacao_c} C):")
    print(_formatar_metricas(metricas))
    print(f"\nGraficos: {pasta_saida}/regime_{args.tipo}_*.png")

    plt.show()


if __name__ == "__main__":
    main()
