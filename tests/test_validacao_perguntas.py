# [Origem: IA] Medido com git blame (ver USO_DE_IA.md).
"""
Validação de integridade do banco de perguntas.

Garante que TODAS as perguntas (do JSON e do fallback embutido) estão bem
formadas: têm os campos certos, 4 opções únicas, e a resposta correta está
entre as opções. Também checa que não há perguntas duplicadas.
"""
from src.common.banco_perguntas import BancoPerguntas


def _todas_as_fontes():
    """Retorna (nome, lista_de_perguntas) para o JSON e para o fallback embutido."""
    banco = BancoPerguntas()
    fontes = [("arquivo/atual", banco.obter_perguntas())]
    # Também valida o banco embutido (usado quando o JSON não existe)
    fontes.append(("embutido", banco._perguntas_padrao()))
    return fontes


def test_todas_perguntas_tem_campos_obrigatorios():
    for nome, perguntas in _todas_as_fontes():
        for i, p in enumerate(perguntas):
            assert "pergunta" in p, f"[{nome}] pergunta {i} sem campo 'pergunta'"
            assert "opcoes" in p, f"[{nome}] pergunta {i} sem campo 'opcoes'"
            assert "resposta_correta" in p, f"[{nome}] pergunta {i} sem 'resposta_correta'"
            assert isinstance(p["pergunta"], str) and p["pergunta"].strip()
            assert isinstance(p["opcoes"], list)


def test_toda_pergunta_tem_quatro_opcoes_unicas():
    for nome, perguntas in _todas_as_fontes():
        for p in perguntas:
            opcoes = p["opcoes"]
            assert len(opcoes) == 4, f"[{nome}] '{p['pergunta']}' não tem 4 opções: {opcoes}"
            assert len(set(opcoes)) == 4, f"[{nome}] '{p['pergunta']}' tem opções repetidas: {opcoes}"


def test_resposta_correta_esta_entre_as_opcoes():
    for nome, perguntas in _todas_as_fontes():
        for p in perguntas:
            assert p["resposta_correta"] in p["opcoes"], (
                f"[{nome}] '{p['pergunta']}' → resposta '{p['resposta_correta']}' "
                f"não está nas opções {p['opcoes']}"
            )


def test_nao_ha_perguntas_duplicadas():
    for nome, perguntas in _todas_as_fontes():
        enunciados = [p["pergunta"] for p in perguntas]
        duplicadas = {e for e in enunciados if enunciados.count(e) > 1}
        assert not duplicadas, f"[{nome}] perguntas duplicadas: {duplicadas}"


def test_nao_ha_perguntas_tecnicamente_ambiguas():
    """
    Verifica pares de perguntas com enunciado diferente mas mesma resposta e
    mesmo tema, que poderiam confundir. Aqui apenas garantimos que não há duas
    perguntas essencialmente iguais (mesmo conjunto de opções + mesma resposta).
    """
    for nome, perguntas in _todas_as_fontes():
        assinaturas = []
        for p in perguntas:
            assinatura = (tuple(sorted(p["opcoes"])), p["resposta_correta"])
            assinaturas.append(assinatura)
        repetidas = {a for a in assinaturas if assinaturas.count(a) > 1}
        assert not repetidas, (
            f"[{nome}] há perguntas com mesmas opções e resposta (possível redundância): {repetidas}"
        )
