"""
Mapeamento entre a saída de controle (potência 0–100% ou 0–1) e a resistência do
potenciômetro eletrônico de 50 kΩ, para uso com o ESP32.

O ESP32 controlará o potenciômetro; aqui definimos a relação:
  sinal de controle [0, 1] ou [0, 100] %  <->  resistência [0, 50] kΩ
"""

from dataclasses import dataclass
import numpy as np


# Resistência total do potenciômetro [Ω]
POTENCIOMETRO_TOTAL_OHMS = 50_000.0


@dataclass
class MapeamentoPotenciometro:
    """
    Converte o sinal de controle (potência normalizada ou percentual) em:
    - resistência [Ω] para o potenciômetro de 50 kΩ;
    - valor para DAC/PWM do ESP32 (8 ou 12 bits).
    """

    resistencia_total_ohms: float = POTENCIOMETRO_TOTAL_OHMS
    # Curva: "linear" ou "log" (curva log dá mais resolução em baixa potência)
    curva: str = "linear"

    def potencia_para_resistencia_ohms(
        self, sinal_controle: float, percentual: bool = False
    ) -> float:
        """
        Converte sinal de controle em resistência [Ω].

        Argumentos:
            sinal_controle: valor entre 0 e 1 (ou 0 e 100 se percentual=True)
            percentual: se True, sinal_controle está em 0–100

        Retorna:
            Resistência em Ω (0 a resistencia_total_ohms).
        """
        u = sinal_controle / 100.0 if percentual else sinal_controle
        u = np.clip(u, 0.0, 1.0)
        if self.curva == "log":
            # Curva logarítmica: mais resolução em baixa potência
            u = (10.0**u - 1.0) / 9.0 if u > 0 else 0.0
        return u * self.resistencia_total_ohms

    def resistencia_para_potencia(
        self, resistencia_ohms: float, percentual: bool = False
    ) -> float:
        """
        Converte resistência [Ω] de volta para sinal de controle (0–1 ou 0–100).
        """
        u = np.clip(
            resistencia_ohms / self.resistencia_total_ohms, 0.0, 1.0
        )
        if self.curva == "log" and u > 0:
            u = np.log10(9.0 * u + 1.0)
        return u * 100.0 if percentual else u

    def potencia_para_dac_8bit(
        self, sinal_controle: float, percentual: bool = False
    ) -> int:
        """
        Mapeia o sinal de controle para valor de DAC 8 bits (0–255).
        Útil para firmware do ESP32.
        """
        u = sinal_controle / 100.0 if percentual else sinal_controle
        u = np.clip(u, 0.0, 1.0)
        return int(round(u * 255))

    def potencia_para_dac_12bit(
        self, sinal_controle: float, percentual: bool = False
    ) -> int:
        """Mapeia o sinal de controle para valor de DAC 12 bits (0–4095)."""
        u = sinal_controle / 100.0 if percentual else sinal_controle
        u = np.clip(u, 0.0, 1.0)
        return int(round(u * 4095))
