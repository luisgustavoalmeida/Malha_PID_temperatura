# Malha PID – Temperatura de Chuveiro

Projeto de modelagem matemática e simulação de uma malha de controle PID para temperatura de um chuveiro elétrico. O controle atua sobre um potenciômetro eletrônico de 50 kΩ (a ser comandado por ESP32).

## Estrutura do projeto

- **`.venv/`** – Ambiente virtual Python (criar com `python -m venv .venv`; ativar com `.venv\Scripts\activate` no Windows).

- **`src/`** – Código principal em Python (variáveis, funções e classes em português)  
  - **`shower_model.py`** – `ParamsChuveiro`, `ModeloChuveiro`: modelo parametrizado do chuveiro  
  - **`pid_controller.py`** – `ParamsPID`, `ControladorPID`: controlador PID com anti-windup  
  - **`potentiometer.py`** – `MapeamentoPotenciometro`: mapeamento para potenciômetro 50 kΩ (ESP32)  
  - **`simulation.py`** – `ConfiguracaoSimulacao`, `AmbienteSimulacao`: simulação chuveiro + PID  
  - **`plotter.py`** – `Plotador`, `plotar_resposta`, `plotar_erro`: gráficos da malha  

- **`environments/`** – Ambientes de teste e aferição  
  - **`step_response.py`** – `AmbienteRespostaDegrau`: resposta ao degrau de setpoint  
  - **`ml_tuning.py`** – `AmbienteTuningML`, `criterio_iae`, `busca_grade`: ajuste por grade (e futuras técnicas de ML)  
  - **`tuning_robusto.py`** – `TuningRobusto`, `RangesTuningRobusto`, `RangeVar`: ajuste robusto variando condições (temperaturas, vazão) e PID (início, fim, passo)

- **`run_simulation.py`** – Script principal: simula e gera gráficos  
- **`run_tuning.py`** – Script de ajuste: resposta ao degrau + busca em grade  
- **`run_tuning_robusto.py`** – Ajuste robusto: varre ranges de temperatura inicial/desejada/ambiente, vazão e Kp/Ki/Kd; encontra o melhor PID para várias condições  

## Parâmetros do chuveiro (ajustáveis)

| Parâmetro | Descrição | Exemplo |
|-----------|-----------|---------|
| `temperatura_inicial_agua` | Temperatura da água na entrada (°C) | 25 |
| `temperatura_desejada` | Setpoint desejado (°C) | 40 |
| `temperatura_ambiente` | Temperatura do ambiente (°C) | 25 |
| `perda_meio` | Perda térmica para o meio (W/K) | 5 |
| `eficiencia_chuveiro` | Eficiência elétrica → térmica (0–1) | 0,92 |
| `potencia_minima` / `potencia_maxima` | Potência do resistor (W) | 0 / 6000 |
| `vazao_minima` / `vazao_maxima` | Vazão de funcionamento (L/min) | 2.5 / 10 |
| `volume_canal` | Volume do canal aquecedor → saída (L) | 0,08 |
| `tensao_nominal_v` | Tensão nominal (V) | 220 |
| `potencia_maxima` | Potência nominal (W) – fabricante | 6000 |
| `eficiencia_chuveiro` | Eficiência (etiqueta) | 0,95 (95%) |

O **tempo de resposta** (atraso até a saída) é calculado a partir da vazão e do volume do canal. A **vazão** pode ser fixa ou obtida da **curva do fabricante** (Vazão × Pressão de entrada em m.c.a.) em `src/curva_vazao_fabricante.py`; na configuração da simulação use `pressao_entrada_mca` para obter a vazão pela curva.

## Como usar

1. Criar e ativar o ambiente virtual (recomendado):
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   ```

2. Instalar dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Simular e ver gráficos:
   ```bash
   python run_simulation.py
   ```
   Os gráficos são salvos em `saida_simulacao/`.

4. Ajustar a malha (ex.: grid search) e comparar respostas:
   ```bash
   python run_tuning.py
   ```
   Resultados em `saida_tuning/`.

5. Ajuste robusto (melhor PID para várias condições de temperatura e vazão):
   ```bash
   python run_tuning_robusto.py
   ```
   Configure os ranges (início, fim, passo) em `run_tuning_robusto.py`. Resultado em `saida_tuning/tuning_robusto_resultado.txt`.

## Potenciômetro 50 kΩ e ESP32

O controle busca sempre a temperatura desejada pelo usuário. A saída do PID (potência normalizada 0–1) é convertida em:

- Resistência equivalente do potenciômetro (0–50 kΩ), e  
- Valor para DAC/PWM no ESP32 (ex.: 0–255 ou 0–4095),

em **`src/potentiometer.py`** (classe `MapeamentoPotenciometro`). O firmware do ESP32 será implementado depois, usando esse mapeamento.

## Modelo matemático (resumo)

- Balanço de energia no aquecedor: potência térmica útil, perdas para o meio, vazão e temperatura de entrada.  
- Atraso de transporte: tempo = volume do canal / vazão (água do aquecedor até a saída).  
- Sensor na saída: medida = temperatura na saída (com esse atraso).  
- PID atua na potência (0–100%) para manter a temperatura de saída no setpoint.

## Próximos passos

- Integrar mais técnicas de ajuste (ex.: Ziegler-Nichols, otimização bayesiana, RL).  
- Programar o ESP32 para ler setpoint/temperatura e comandar o potenciômetro de 50 kΩ conforme o mapeamento definido aqui.
