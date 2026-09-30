"""M10 – Gráficos para os relatórios em PDF (RF-07), gerados com Matplotlib.

As imagens são estáticas (PNG ou SVG) e vão embutidas no PDF pelo Desktop (OpenPDF).
O Matplotlib é importado só quando um gráfico é pedido, para não pesar nas demais operações.
"""

from .figuras import FORMATOS, curva_cota_area_volume, serie_temporal

__all__ = ["FORMATOS", "curva_cota_area_volume", "serie_temporal"]
