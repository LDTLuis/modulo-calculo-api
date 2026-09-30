"""Infraestrutura comum dos cálculos de engenharia (M3–M8).

Cada cálculo declara as entradas que a tela do Desktop deve coletar (nome, unidade, faixa
válida) e uma função que recebe os valores já convertidos para as unidades canônicas e
registra cada passo numa `Memoria` — a memória de cálculo que vai para o relatório.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from . import unidades
from .erros import ErroValidacao, UnidadeDesconhecida
from .resultado import Resultado, Severidade


# --- entradas -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Entrada:
    nome: str
    descricao: str
    unidade: str = "-"  # unidade canônica em que a função recebe o valor
    minimo: float | None = None
    minimo_inclusivo: bool = True
    maximo: float | None = None
    inteiro: bool = False
    padrao: float | None = None  # com padrão, o campo é opcional
    opcional: bool = False  # opcional sem padrão: a função recebe None

    @property
    def obrigatoria(self) -> bool:
        return self.padrao is None and not self.opcional

    def para_dict(self) -> dict:
        return {
            "nome": self.nome,
            "descricao": self.descricao,
            "unidade": self.unidade,
            "unidades_aceitas": unidades.unidades_da_dimensao(unidades.dimensao(self.unidade))
            if self.unidade != "-"
            else ["-"],
            "obrigatoria": self.obrigatoria,
            "padrao": self.padrao,
            "minimo": self.minimo,
            "minimo_inclusivo": self.minimo_inclusivo,
            "maximo": self.maximo,
            "inteiro": self.inteiro,
        }


# Peso específico da água, comum a vários cálculos.
GAMA_W = Entrada(
    "gama_w",
    "Peso específico da água (γw); a apostila usa 10 kN/m³ nos exemplos",
    "kN/m3",
    minimo=0,
    minimo_inclusivo=False,
    padrao=9.81,
)


class ErroEntradas(ErroValidacao):
    """Uma ou mais entradas inválidas; `erros` traz o campo de cada problema para a tela."""

    codigo = "ENTRADAS_INVALIDAS"

    def __init__(self, erros: list[dict]):
        super().__init__("; ".join(f"{e['campo']}: {e['mensagem']}" for e in erros))
        self.erros = erros


def erro_campo(campo: str, mensagem: str, codigo: str = "VALOR_INVALIDO") -> ErroEntradas:
    return ErroEntradas([{"campo": campo, "codigo": codigo, "mensagem": mensagem}])


# --- memória de cálculo ---------------------------------------------------------------


_SOBRESCRITO = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def fmt(valor: float) -> str:
    """Número para a memória de cálculo em pt-BR: vírgula decimal, até 6 algarismos e
    notação científica legível para valores muito pequenos/grandes (1e-05 → 1·10⁻⁵)."""
    texto = f"{valor:.6g}"
    if "e" in texto:
        mantissa, expoente = texto.split("e")
        texto = f"{mantissa}·10{str(int(expoente)).translate(_SOBRESCRITO)}"
    return texto.replace(".", ",")


@dataclass(frozen=True, slots=True)
class Passo:
    descricao: str
    formula: str
    substituicao: str
    valor: float
    unidade: str

    def para_dict(self) -> dict:
        return {
            "descricao": self.descricao,
            "formula": self.formula,
            "substituicao": self.substituicao,
            "valor": self.valor,
            "unidade": self.unidade,
        }


@dataclass(slots=True)
class Memoria:
    passos: list[Passo] = field(default_factory=list)
    premissas: list[str] = field(default_factory=list)
    conclusoes: list[str] = field(default_factory=list)
    # nome -> (valor, origem); preenchido por `executar` com os limites declarados pelo cálculo
    limites: dict[str, tuple[float, str]] = field(default_factory=dict)

    def passo(self, descricao: str, formula: str, substituicao: str, valor: float, unidade: str) -> float:
        """Registra o passo e devolve o valor, para encadear: `x = mem.passo(...)`."""
        sufixo = "" if unidade == "-" else f" {unidade}"
        self.passos.append(Passo(descricao, formula, f"{substituicao} = {fmt(valor)}{sufixo}", valor, unidade))
        return valor

    def premissa(self, texto: str) -> None:
        if texto not in self.premissas:
            self.premissas.append(texto)

    def conclusao(self, texto: str) -> None:
        self.conclusoes.append(texto)

    def limite(self, nome: str) -> float:
        """Valor do critério (ex.: FS mínimo), registrando sua origem como premissa."""
        valor, origem = self.limites[nome]
        self.premissa(f"{nome} = {fmt(valor)} ({origem})")
        return valor


# --- critérios de segurança ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Limite:
    """Critério de aceitação configurável na Central (`configuracao.limites_calculo`)."""

    nome: str
    descricao: str
    padrao: float

    def para_dict(self) -> dict:
        return {"nome": self.nome, "descricao": self.descricao, "padrao": self.padrao}


def resultado(
    mem: Memoria,
    calculo_id: str,
    descricao: str,
    valor: float,
    unidade: str,
    fonte: str,
    severidade: Severidade = Severidade.OK,
    limite: float | None = None,
) -> Resultado:
    """Monta um `Resultado` com as premissas registradas até aqui na memória."""
    return Resultado(
        calculo=calculo_id,
        descricao=descricao,
        valor=valor,
        unidade=unidade,
        severidade=severidade,
        limite=limite,
        premissas=tuple(mem.premissas),
        fonte=fonte,
    )


def classificar_fs(fs: float, fs_min: float) -> Severidade:
    """FS ≥ mínimo: OK · 1 ≤ FS < mínimo: ALERTA (não atende o critério) · FS < 1: CRITICO."""
    if fs >= fs_min:
        return Severidade.OK
    return Severidade.ALERTA if fs >= 1 else Severidade.CRITICO


# --- registro ---------------------------------------------------------------------------

FuncaoCalculo = Callable[[Mapping[str, float | None], Memoria], list[Resultado]]


@dataclass(frozen=True, slots=True)
class DefinicaoCalculo:
    id: str
    titulo: str
    fonte: str
    entradas: tuple[Entrada, ...]
    funcao: FuncaoCalculo
    limites: tuple[Limite, ...] = ()

    @property
    def modulo(self) -> str:
        return self.id.split(".")[0]

    def para_dict(self) -> dict:
        return {
            "id": self.id,
            "modulo": self.modulo,
            "titulo": self.titulo,
            "fonte": self.fonte,
            "entradas": [e.para_dict() for e in self.entradas],
            "limites": [lim.para_dict() for lim in self.limites],
        }


@dataclass(frozen=True, slots=True)
class ResultadoCalculo:
    definicao: DefinicaoCalculo
    entradas: dict[str, float | None]
    resultados: list[Resultado]
    memoria: Memoria


REGISTRO: dict[str, DefinicaoCalculo] = {}


def calculo(
    id: str,
    titulo: str,
    fonte: str,
    entradas: tuple[Entrada, ...],
    limites: tuple[Limite, ...] = (),
):
    """Decorador que registra a função de cálculo sob `id` (ex.: 'hidrostatica.empuxo')."""

    def registrar(funcao: FuncaoCalculo) -> FuncaoCalculo:
        if id in REGISTRO:
            raise ValueError(f"Cálculo duplicado: {id}")
        REGISTRO[id] = DefinicaoCalculo(id, titulo, fonte, entradas, funcao, limites)
        return funcao

    return registrar


def executar(
    id: str,
    brutas: Mapping[str, object],
    limites_configurados: Mapping[str, float] | None = None,
) -> ResultadoCalculo:
    """Valida/converte as entradas e executa o cálculo.

    Cada entrada bruta é um número (já na unidade canônica) ou {"valor": n, "unidade": u}.
    Todos os problemas de entrada são reunidos num único `ErroEntradas`.
    `limites_configurados` (da Central) sobrepõe o padrão de cada `Limite` declarado.
    """
    definicao = REGISTRO.get(id)
    if definicao is None:
        raise ErroValidacao(f"Cálculo desconhecido: {id!r}", codigo="CALCULO_DESCONHECIDO")

    erros: list[dict] = []
    conhecidas = {e.nome for e in definicao.entradas}
    for nome in brutas:
        if nome not in conhecidas:
            erros.append({"campo": nome, "codigo": "CAMPO_DESCONHECIDO", "mensagem": "campo não pertence a este cálculo"})

    valores: dict[str, float | None] = {}
    memoria = Memoria()
    configurados = limites_configurados or {}
    for lim in definicao.limites:
        if lim.nome in configurados:
            memoria.limites[lim.nome] = (configurados[lim.nome], "configuração da Central")
        else:
            memoria.limites[lim.nome] = (lim.padrao, "padrão do motor")
    for entrada in definicao.entradas:
        try:
            valores[entrada.nome] = _ler_entrada(entrada, brutas.get(entrada.nome))
        except ErroEntradas as e:
            erros += e.erros
            continue
        if entrada.nome not in brutas and entrada.padrao is not None:
            memoria.premissa(f"{entrada.nome} = {fmt(entrada.padrao)} {entrada.unidade} (padrão)")
    if erros:
        raise ErroEntradas(erros)

    resultados = definicao.funcao(valores, memoria)
    return ResultadoCalculo(definicao, valores, resultados, memoria)


def _ler_entrada(entrada: Entrada, bruto: object) -> float | None:
    nome = entrada.nome
    if bruto is None:
        if entrada.obrigatoria:
            raise erro_campo(nome, "campo obrigatório", "CAMPO_AUSENTE")
        return entrada.padrao

    unidade = entrada.unidade
    if isinstance(bruto, Mapping):
        unidade = bruto.get("unidade") or entrada.unidade
        bruto = bruto.get("valor")
        if bruto is None:
            raise erro_campo(nome, "informe 'valor'", "CAMPO_AUSENTE")
    if isinstance(bruto, bool) or not isinstance(bruto, (int, float)) or not math.isfinite(bruto):
        raise erro_campo(nome, f"valor deve ser numérico, recebido {bruto!r}")

    valor = float(bruto)
    if unidade != entrada.unidade:
        valor = _converter(entrada, valor, unidade)

    if entrada.inteiro and not valor.is_integer():
        raise erro_campo(nome, "deve ser um número inteiro")
    if entrada.minimo is not None:
        if valor < entrada.minimo or (not entrada.minimo_inclusivo and valor == entrada.minimo):
            sinal = "≥" if entrada.minimo_inclusivo else ">"
            raise erro_campo(nome, f"deve ser {sinal} {fmt(entrada.minimo)} {entrada.unidade}".rstrip(" -"), "FORA_DO_INTERVALO")
    if entrada.maximo is not None and valor > entrada.maximo:
        raise erro_campo(nome, f"deve ser ≤ {fmt(entrada.maximo)} {entrada.unidade}".rstrip(" -"), "FORA_DO_INTERVALO")
    return valor


def _converter(entrada: Entrada, valor: float, unidade: object) -> float:
    try:
        if entrada.unidade == "-" or unidades.dimensao(unidade) is not unidades.dimensao(entrada.unidade):  # type: ignore[arg-type]
            raise erro_campo(
                entrada.nome,
                f"unidade {unidade!r} incompatível (esperado: {entrada.unidade})",
                "UNIDADE_INCOMPATIVEL",
            )
        return float(unidades.converter(valor, unidade, entrada.unidade))  # type: ignore[arg-type]
    except UnidadeDesconhecida:
        raise erro_campo(entrada.nome, f"unidade desconhecida: {unidade!r}", "UNIDADE_DESCONHECIDA") from None
