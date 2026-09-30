"""Hierarquia de erros do motor. Todo erro esperado carrega um código estável para o Desktop."""


class DamiqErro(Exception):
    codigo = "ERRO"

    def __init__(self, mensagem: str, codigo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        if codigo is not None:
            self.codigo = codigo


class ErroValidacao(DamiqErro):
    """Entrada inválida: o chamador pode corrigir e reenviar (código de saída 1)."""

    codigo = "ENTRADA_INVALIDA"


class UnidadeDesconhecida(ErroValidacao):
    codigo = "UNIDADE_DESCONHECIDA"


class UnidadeIncompativel(ErroValidacao):
    codigo = "UNIDADE_INCOMPATIVEL"
