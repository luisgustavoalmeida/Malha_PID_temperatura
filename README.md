# Modelo computacional para ajuste de PID — Controle de temperatura em chuveiros elétricos

Simulador da malha de controle PID com modelo parametrizado do equipamento, para **ajustar ganhos (Kp, Ki, Kd) em software antes da implementação no hardware**.

---

## Sobre o projeto

Este repositório contém um **modelo computacional** que replica o comportamento de um chuveiro elétrico com base em dados do fabricante e em medições empíricas. O objetivo é permitir o **ajuste da malha PID em ambiente de simulação**, reduzindo tentativa e erro no equipamento real.

A ideia do projeto é **avaliar a viabilidade de um trabalho futuro** em que um **microcontrolador (ESP32 ou ARM)** será usado para controlar o chuveiro em tempo real usando **software embarcado**. Esta etapa atual (modelo + simulação + tuning) corresponde à **primeira etapa**; a **segunda etapa** será a implementação no microcontrolador — firmware para leitura de setpoint e temperatura, execução do PID e comando do atuador (potenciômetro eletrônico 50 kΩ instalado junto à linha de potência do chuveiro).

- **Equipamento:** parâmetros como potência nominal, eficiência, volume do canal e faixa de vazão são configuráveis e refletem o chuveiro real.
- **Meio e condições de uso:** temperatura da água de entrada, temperatura ambiente, perda térmica e vazão podem ser alterados para simular diferentes cenários.
- **Vazão:** informada diretamente na simulação (em L/min).

---

## Funcionalidades

- Simulação em malha fechada: setpoint → PID → potência → modelo do chuveiro → temperatura de saída.
- Controlador PID com anti-windup; saída em potência normalizada (0–1), compatível com mapeamento para potenciômetro 50 kΩ e DAC/PWM no ESP32.
- Resposta ao degrau de setpoint e geração de gráficos (temperatura, potência, erro).
- Ajuste por **grid search** (busca em grade) com critérios configuráveis (IAE, ITAE, ISE, overshoot, tempo de subida, etc.).
- **Tuning robusto:** varredura de temperaturas, vazão e ganhos PID para obter um conjunto (Kp, Ki, Kd) que se comporta bem em várias condições.
- Curva do fabricante (vazão) disponível como referência opcional; simulação usa apenas vazão informada diretamente.

---

## Requisitos

- **Python** 3.10 ou superior (recomendado 3.12.9+).
- Dependências (ver `requirements.txt`):
  - `numpy`, `matplotlib`, `scipy` — simulação e gráficos.
  - `scikit-learn` — tuning (grid search e critérios).
  - `tqdm` — barra de progresso no tuning robusto.

---

## Instalação

```bash
# Clonar o repositório (ou baixar e extrair)
git clone <url-do-repositorio>
cd Malha_PID_temperatura

# Criar e ativar ambiente virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Linux/macOS

# Instalar dependências
pip install -r requirements.txt
```

---

## Uso

Fluxo sugerido: configurar parâmetros do chuveiro e do meio → **ajustar o PID na simulação** → usar os ganhos encontrados no equipamento real.

| Comando | Descrição |
|--------|------------|
| `python run_simulation.py` | Roda a simulação com os ganhos atuais e gera gráficos em `saida_simulacao/`. |
| `python run_tuning.py` | Resposta ao degrau + grid search; resultados em `saida_tuning/`. |
| `python run_tuning_robusto.py` | Tuning robusto em vários cenários; resultado em `saida_tuning/tuning_robusto_resultado.txt`. |
| `python plotar_curva_vazao.py` | (Opcional) Gera gráfico da curva do fabricante em `saida_simulacao/curva_vazao_fabricante.png`. |

Os parâmetros do chuveiro, do PID e da simulação são editados nos próprios scripts (`run_simulation.py`, `run_tuning.py`, `run_tuning_robusto.py`). Para o tuning robusto, os intervalos (início, fim, passo) de cada variável são definidos em `RangesTuningRobusto` em `run_tuning_robusto.py`.

---

## Estrutura do projeto

| Caminho | Descrição |
|--------|------------|
| **`src/`** | Núcleo do modelo e da simulação (nomes em português). |
| `src/constants.py` | Constantes físicas (calor específico e densidade da água). |
| `src/shower_model.py` | `ParamsChuveiro`, `ModeloChuveiro` — modelo parametrizado do chuveiro. |
| `src/pid_controller.py` | `ParamsPID`, `ControladorPID` — PID com anti-windup. |
| `src/potentiometer.py` | `MapeamentoPotenciometro` — potenciômetro 50 kΩ e DAC/PWM (ESP32). |
| `src/simulation.py` | `ConfiguracaoSimulacao`, `AmbienteSimulacao` — simulação chuveiro + PID. |
| `src/plotter.py` | `Plotador`, `plotar_resposta`, `plotar_erro` — gráficos. |
| `src/curva_vazao_fabricante.py` | Curva do fabricante (referência); simulação usa `vazao_lmin` diretamente. |
| **`environments/`** | Ambientes de teste e tuning. |
| `environments/base_environment.py` | `AmbienteBase` — base para ambientes de simulação. |
| `environments/step_response.py` | `AmbienteRespostaDegrau` — resposta ao degrau. |
| `environments/ml_tuning.py` | `AmbienteTuningML`, critérios (IAE, ITAE, overshoot, etc.), busca em grade. |
| `environments/tuning_robusto.py` | `TuningRobusto`, `RangesTuningRobusto`, `RangeVar` — tuning robusto. |
| **Raiz** | Scripts executáveis. |
| `run_simulation.py` | Simulação e gráficos. |
| `run_tuning.py` | Resposta ao degrau + grid search. |
| `run_tuning_robusto.py` | Tuning robusto (multiprocessing). |
| `plotar_curva_vazao.py` | Gráfico da curva do fabricante (opcional). |
| `requirements.txt` | Dependências Python. |

---

## Parâmetros do modelo

O modelo distingue parâmetros de **equipamento**, de **meio** e de **uso**.

| Parâmetro | Descrição | Exemplo | Origem |
|-----------|-----------|---------|--------|
| `temperatura_inicial_agua` | Temperatura da água na entrada (°C) | 19 | Meio |
| `temperatura_desejada` | Setpoint (°C) | 38 | Uso |
| `temperatura_ambiente` | Temperatura do ambiente (°C) | 23 | Meio |
| `perda_meio` | Perda térmica para o meio (W/K) | 2 | Meio |
| `eficiencia_chuveiro` | Eficiência elétrica → térmica (0–1) | 0,95 | Equipamento |
| `potencia_minima` / `potencia_maxima` | Potência do resistor (W) | 0 / 6000 | Equipamento |
| `vazao_minima` / `vazao_maxima` | Faixa de vazão (L/min) | 2,5 / 10 | Equipamento / meio |
| `volume_canal` | Volume do canal aquecedor → saída (L) | 0,7 | Equipamento |
| `tensao_nominal_v` | Tensão nominal (V) | 220 | Equipamento |

O atraso de transporte (tempo até a saída) é calculado a partir da **vazão** e do **volume do canal**. A vazão na simulação é sempre definida por **`vazao_lmin`** em `ConfiguracaoSimulacao` (L/min).

---

## Modelo matemático (resumo)

- **Balanço de energia** no aquecedor: potência térmica útil, perdas para o meio, vazão e temperatura de entrada.
- **Atraso de transporte:** tempo = volume do canal / vazão (da saída do aquecedor até o ponto de medição).
- **Sensor:** temperatura na saída, com esse atraso.
- **PID:** atua na potência (0–100%) para manter a temperatura de saída no setpoint.

Isso permite testar diferentes condições de meio e ganhos do PID sem alterar o hardware.

---

## Potenciômetro 50 kΩ e microcontrolador (implementação real)

A saída do PID no modelo é potência normalizada (0–1). No **equipamento real**, essa saída é convertida em resistência do potenciômetro (0–50 kΩ) e em valor para DAC/PWM pela classe **`MapeamentoPotenciometro`** em `src/potentiometer.py`. Os ganhos ajustados na simulação podem ser usados diretamente no firmware embarcado (ESP32, ARM ou outro microcontrolador).

---

## Tecnologias

Python 3 · NumPy · Matplotlib · SciPy · scikit-learn · tqdm

---

## Próximos passos

- **Primeira etapa (atual):** inclusão de outras técnicas de ajuste no modelo (ex.: Ziegler-Nichols, otimização bayesiana).
- **Segunda etapa (software embarcado):** implementação em microcontrolador (ESP32 ou ARM) — firmware para leitura de setpoint e temperatura, execução do PID e comando do atuador (potenciômetro 50 kΩ), utilizando o mapeamento e os ganhos validados neste repositório.
