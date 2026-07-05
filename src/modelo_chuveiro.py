"""
Modelo matemático parametrizado do chuveiro elétrico.

Descreve o balanço de energia na saída, com atraso de transporte:
- Temperatura na saída = f(potência, vazão, temperatura de entrada, perdas, atraso).
- Tempo de resposta (atraso) = volume do canal / vazão [s].
- O sensor de temperatura fica na saída do chuveiro; a saída do modelo é essa temperatura.
"""

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

from .constantes import CALOR_ESPECIFICO_AGUA, DENSIDADE_AGUA

ModoControlePotencia = Literal["linear", "degrau"]


@dataclass
class ParamsChuveiro:
    """
    Parâmetros físicos e elétricos do chuveiro e do meio.
    Todos os valores são ajustáveis para refletir o equipamento real.
    """

    # Temperatura da água na entrada do chuveiro [°C] (condição inicial da planta)
    temperatura_inicial_agua: float = 18.0
    # Setpoint desejado pelo usuário [°C] (alvo da malha de controle)
    temperatura_desejada: float = 38.0
    # Temperatura do ambiente [°C] — usada no cálculo de perdas térmicas para o meio
    temperatura_ambiente: float = 20.0

    # Condutância térmica equivalente [W/K]: perda = perda_meio × (T_água − T_ambiente)
    perda_meio: float = 0.2

    # Fração da potência elétrica convertida em calor na água (0 a 1). Fabricante: 95%
    eficiencia_chuveiro: float = 0.95

    # Tensão nominal de referência [V] (equipamento: 220 V)
    tensao_nominal_v: float = 220.0

    # Potência mínima e máxima do resistor [W] (nominal: 6000 W)
    potencia_minima: float = 0.0
    potencia_maxima: float = 6000.0

    # "linear" = potência contínua; "degrau" = quantização (potenciômetro digital / ESP32)
    modo_controle_potencia: ModoControlePotencia = "degrau"
    # Níveis discretos entre mínima e máxima (modo "degrau").
    # Ex.: 100 → índices 0..100; nível 0 = 0 W, nível 100 = potencia_maxima
    numero_passos_potencia: int = 100

    # Faixa de vazão válida do equipamento [L/min] (limita entradas na simulação)
    vazao_minima: float = 1.8
    vazao_maxima: float = 10.0

    # Volume do canal aquecedor até a saída [L]. Define atraso de transporte: τ = volume / vazão
    volume_canal: float = 0.850

    # Limites de saturação do modelo [°C] (segurança e clipping interno)
    temperatura_minima: float = 10.0
    temperatura_maxima: float = 45.0

    def vazao_para_m3s(self, vazao_lmin: float) -> float:
        """Converte vazão de L/min para m³/s."""
        return (vazao_lmin / 60.0) * 1e-3

    def tempo_resposta_s(self, vazao_lmin: float) -> float:
        """
        Tempo que a água leva do ponto de aquecimento até a saída [s].
        Depende da vazão: tempo = volume do canal / vazão.
        """
        if vazao_lmin <= 0:
            return 60.0  # Valor alto para evitar divisão por zero
        vazao_m3s = self.vazao_para_m3s(vazao_lmin)
        volume_m3 = self.volume_canal / 1000.0  # [L] -> [m³]
        return volume_m3 / vazao_m3s

    def passo_potencia_w(self) -> float:
        """Incremento de potência [W] entre dois níveis consecutivos (modo degrau)."""
        faixa = self.potencia_maxima - self.potencia_minima
        if self.numero_passos_potencia <= 0:
            return faixa
        return faixa / self.numero_passos_potencia

    def aplicar_controle_potencia(self, potencia_w: float) -> float:
        """
        Limita e, se modo "degrau", quantiza a potência ao nível discreto mais próximo.

        Os níveis vão de 0 a numero_passos_potencia entre potencia_minima e potencia_maxima.
        Ex.: numero_passos_potencia=100 → índices 0..100 (0 W .. potencia_maxima).
        """
        pot_min = self.potencia_minima
        pot_max = self.potencia_maxima
        pot_clip = float(np.clip(potencia_w, pot_min, pot_max))

        if self.modo_controle_potencia != "degrau":
            return pot_clip

        n_passos = self.numero_passos_potencia
        if n_passos <= 0:
            return pot_clip

        faixa = pot_max - pot_min
        if faixa <= 0:
            return pot_min

        indice = int(round((pot_clip - pot_min) / faixa * n_passos))
        indice = int(np.clip(indice, 0, n_passos))
        return float(pot_min + (indice / n_passos) * faixa)


class ModeloChuveiro:
    """
    Modelo computacional do chuveiro com atraso de transporte e perdas.

    Entradas de controle:
    - potencia_w: potência elétrica solicitada [W]
    - vazao_lmin: vazão de água [L/min] (afeta atraso e ganho térmico)

    A potência efetiva segue ParamsChuveiro.modo_controle_potencia:
    linear (contínua) ou degrau (quantização do potenciômetro digital).

    Saída:
    - temperatura_saida: temperatura na saída do chuveiro [°C], onde está o sensor.
    """

    def __init__(self, params: Optional[ParamsChuveiro] = None):
        self.params = params or ParamsChuveiro()
        # Estado interno: temperatura na saída e no aquecedor
        self._temperatura_saida: float = self.params.temperatura_inicial_agua
        self._temperatura_aquecedor: float = self.params.temperatura_inicial_agua
        # Fila para atraso de transporte: número de amostras = tempo_resposta / passo_tempo
        self._buffer_temperatura: list = []
        self._passo_tempo: float = 0.1  # Passo de simulação [s]
        self._numero_amostras_atraso: int = 1
        self._ultima_potencia_aplicada_w: float = 0.0

    def definir_passo_tempo(self, passo_tempo: float) -> None:
        """Define o passo de integração da simulação [s]."""
        self._passo_tempo = passo_tempo

    def _atualizar_buffer_atraso(self, vazao_lmin: float) -> None:
        """Recalcula quantas amostras de atraso usar conforme a vazão."""
        tau = self.params.tempo_resposta_s(vazao_lmin)
        numero_amostras = max(1, int(round(tau / self._passo_tempo)))
        self._numero_amostras_atraso = numero_amostras
        # Ajustar tamanho do buffer
        while len(self._buffer_temperatura) > numero_amostras:
            self._buffer_temperatura.pop(0)
        while len(self._buffer_temperatura) < numero_amostras:
            self._buffer_temperatura.insert(0, self._temperatura_aquecedor)

    def passo(
        self,
        potencia_w: float,
        vazao_lmin: float,
        temperatura_entrada: Optional[float] = None,
    ) -> float:
        """
        Executa um passo de simulação.

        Argumentos:
            potencia_w: potência elétrica solicitada [W]
            vazao_lmin: vazão [L/min]
            temperatura_entrada: temperatura da água na entrada [°C]; se None, usa temperatura_inicial_agua.

        Retorna:
            Temperatura na saída [°C].
        """
        temp_entrada = (
            temperatura_entrada
            if temperatura_entrada is not None
            else self.params.temperatura_inicial_agua
        )
        temp_ambiente = self.params.temperatura_ambiente
        eficiencia = self.params.eficiencia_chuveiro
        perda_meio = self.params.perda_meio

        pot_limite = self.params.aplicar_controle_potencia(potencia_w)
        self._ultima_potencia_aplicada_w = pot_limite
        vazao_limite = np.clip(vazao_lmin, self.params.vazao_minima, self.params.vazao_maxima)

        # Vazão em massa [kg/s]
        vazao_m3s = self.params.vazao_para_m3s(vazao_limite)
        vazao_massa = DENSIDADE_AGUA * vazao_m3s  # kg/s

        # Potência térmica entregue à água (após eficiência)
        pot_termica = eficiencia * pot_limite

        # Perda para o meio: proporcional à diferença com o ambiente
        perda_w = perda_meio * (self._temperatura_aquecedor - temp_ambiente)

        # Balanço no aquecedor: modelo de primeira ordem (Euler)
        # Temperatura de equilíbrio aproximada + dinâmica com constante de tempo
        if vazao_massa > 1e-6:
            temp_equilibrio = temp_entrada + (pot_termica - perda_w) / (vazao_massa * CALOR_ESPECIFICO_AGUA)
            temp_equilibrio = np.clip(
                temp_equilibrio,
                self.params.temperatura_minima,
                self.params.temperatura_maxima,
            )
            volume_m3 = self.params.volume_canal / 1000.0  # [L] -> [m³]
            tau_dinamica = (DENSIDADE_AGUA * volume_m3 * CALOR_ESPECIFICO_AGUA) / (
                vazao_massa * CALOR_ESPECIFICO_AGUA
            )
            alfa = self._passo_tempo / (tau_dinamica + self._passo_tempo)
            self._temperatura_aquecedor = (
                (1 - alfa) * self._temperatura_aquecedor + alfa * temp_equilibrio
            )
        else:
            # Sem vazão: apenas perda térmica
            volume_m3 = self.params.volume_canal / 1000.0  # [L] -> [m³]
            self._temperatura_aquecedor = self._temperatura_aquecedor - (
                perda_w * self._passo_tempo
            ) / (DENSIDADE_AGUA * volume_m3 * CALOR_ESPECIFICO_AGUA)
            self._temperatura_aquecedor = np.clip(
                self._temperatura_aquecedor,
                temp_ambiente,
                self.params.temperatura_maxima,
            )

        self._temperatura_aquecedor = np.clip(
            self._temperatura_aquecedor,
            self.params.temperatura_minima,
            self.params.temperatura_maxima,
        )

        # Atraso de transporte: saída = temperatura que saiu do aquecedor há tau segundos
        self._atualizar_buffer_atraso(vazao_limite)
        self._buffer_temperatura.append(self._temperatura_aquecedor)
        self._temperatura_saida = self._buffer_temperatura.pop(0)

        return float(self._temperatura_saida)

    def reiniciar(self, temperatura_inicial: Optional[float] = None) -> None:
        """Reinicia o estado do modelo (temperaturas e buffer de atraso)."""
        temp_inicial = (
            temperatura_inicial
            if temperatura_inicial is not None
            else self.params.temperatura_inicial_agua
        )
        self._temperatura_saida = temp_inicial
        self._temperatura_aquecedor = temp_inicial
        self._buffer_temperatura = []

    @property
    def ultima_potencia_aplicada_w(self) -> float:
        """Potência efetiva do último passo [W] (após limite e quantização em degraus)."""
        return self._ultima_potencia_aplicada_w

    @property
    def temperatura_saida(self) -> float:
        """Temperatura atual na saída do chuveiro [°C] (posição do sensor)."""
        return self._temperatura_saida

    @property
    def temperatura_aquecedor(self) -> float:
        """
        Temperatura atual no volume do aquecedor [°C].
        Útil para diagnóstico e firmware; a malha de controle usa apenas temperatura_saida.
        """
        return self._temperatura_aquecedor
