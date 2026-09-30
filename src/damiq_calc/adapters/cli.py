"""Ponto de entrada chamado pelo Desktop via ProcessBuilder.

    python -m damiq_calc [--entrada req.json] [--saida resp.json]

Sem argumentos, lê a requisição do stdin e escreve a resposta no stdout (UTF-8).
Códigos de saída: 0 = sucesso, 1 = entrada inválida, 2 = erro interno (traceback no stderr).
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from damiq_calc.core.erros import ErroValidacao

from .contrato import processar, resposta_erro

SAIDA_OK = 0
SAIDA_ENTRADA_INVALIDA = 1
SAIDA_ERRO_INTERNO = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="damiq_calc", description="Motor de cálculo DAMIQ")
    parser.add_argument("--entrada", type=Path, help="arquivo JSON da requisição (padrão: stdin)")
    parser.add_argument("--saida", type=Path, help="arquivo JSON da resposta (padrão: stdout)")
    args = parser.parse_args(argv)

    operacao = None
    try:
        texto = _ler(args.entrada)
        requisicao = json.loads(texto)
        if isinstance(requisicao, dict):
            operacao = requisicao.get("operacao")
        resposta = processar(requisicao)
        codigo = SAIDA_OK
    except json.JSONDecodeError as e:
        resposta = resposta_erro(None, "JSON_INVALIDO", f"JSON inválido: {e}")
        codigo = SAIDA_ENTRADA_INVALIDA
    except ErroValidacao as e:
        resposta = resposta_erro(operacao, e.codigo, e.mensagem, getattr(e, "erros", None))
        codigo = SAIDA_ENTRADA_INVALIDA
    except Exception as e:  # noqa: BLE001 – a resposta JSON precisa sair mesmo em falha interna
        traceback.print_exc(file=sys.stderr)
        resposta = resposta_erro(operacao, "ERRO_INTERNO", f"{type(e).__name__}: {e}")
        codigo = SAIDA_ERRO_INTERNO

    _escrever(resposta, args.saida)
    return codigo


def _ler(caminho: Path | None) -> str:
    dados = caminho.read_bytes() if caminho else sys.stdin.buffer.read()
    return dados.decode("utf-8-sig")


def _escrever(resposta: dict, caminho: Path | None) -> None:
    # Bytes UTF-8 explícitos: no Windows o stdout padrão usa cp1252.
    dados = json.dumps(resposta, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if caminho:
        caminho.write_bytes(dados)
    else:
        sys.stdout.buffer.write(dados)
        sys.stdout.buffer.flush()
