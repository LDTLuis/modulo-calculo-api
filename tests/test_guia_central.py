"""O guia da Central (docs/central/guia-configuracao.md) é gerado do schema e deve estar atualizado."""

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_guia_da_central_esta_atualizado():
    """Falhou? Rode `python scripts/gerar_guia_central.py` (e regenere o PDF) e faça commit de docs/central/."""
    spec = importlib.util.spec_from_file_location("gerar_guia_central", RAIZ / "scripts" / "gerar_guia_central.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    assert (RAIZ / "docs/central/guia-configuracao.md").read_text(encoding="utf-8") == modulo.gerar()
